import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user, require_role, validar_acceso_espacio
from app.core.database import get_db
from app.domain.models import IngestionJob
from app.schemas.ingestion_schemas import (
    FileInspectionResponse,
    IngestionValidationResponse,
    IngestionProcessResponse,
    JobStatusResponse,
    IngestionHistoryItem,
)
from app.services.ingestion_service import (
    inspect_uploaded_file,
    validar_archivo_ingesta,
    ejecutar_ingesta_atomica,
    run_ingestion_pipeline,
    encolar_y_procesar_ingesta,
    enriquecer_asistencia_retroactiva,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/inspect",
    response_model=FileInspectionResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspeccionar archivo, detectar cabeceras y realizar Schema Matching (RF03)",
)
async def inspect_file_endpoint(
    tipo: str = Query(..., description="Tipo de dataset: marcajes_torniquete, asistencia, vehicular, academico, curricular, custom"),
    espacio_id: int = Query(1, description="ID del espacio institucional (1: biblioteca, 2: estacionamiento)"),
    file: UploadFile = File(...),
    current_user=Depends(require_role("SuperAdmin", "Directivo", "Admin_Sistema", "Director_Recinto")),
):
    """
    Inspecciona en memoria volátil la estructura del archivo subido.
    Detecta la fila de cabecera real, ejecuta el matching de columnas con semáforo
    y entrega una muestra sanitizada libre de PII según la Ley N° 21.719.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo no proporcionado")

    validar_acceso_espacio(espacio_id, current_user)

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido se encuentra vacío")

    return await inspect_uploaded_file(
        file_bytes=file_bytes,
        filename=file.filename,
        tipo=tipo,
        espacio_id=espacio_id,
    )


@router.post(
    "/validate",
    response_model=IngestionValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validación previa de colisiones y enlace curricular (RF04, RF30)",
)
async def validate_file_endpoint(
    tipo: str = Query("marcajes_torniquete", description="Tipo de dataset: marcajes_torniquete, asistencia, vehicular, academico, curricular, custom"),
    espacio_id: int = Query(1, description="ID del espacio institucional (1: biblioteca, 2: estacionamiento)"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("SuperAdmin", "Directivo", "Admin_Sistema", "Director_Recinto")),
):
    """
    Calcula el hash SHA-256 en memoria volátil, extrae el rango temporal, evalúa
    solapamiento de registros en SQL Server y detecta la clave de enlace curricular óptima.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo no proporcionado")

    validar_acceso_espacio(espacio_id, current_user)

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido se encuentra vacío")

    return await validar_archivo_ingesta(
        file_bytes=file_bytes,
        filename=file.filename,
        tipo=tipo,
        espacio_id=espacio_id,
        db=db,
    )


@router.post(
    "/process",
    response_model=IngestionProcessResponse,
    status_code=status.HTTP_200_OK,
    summary="Procesamiento y carga atómica con resolución de colisiones y cruce curricular (RF04, RF30)",
)
async def process_file_endpoint(
    tipo: str = Query("marcajes_torniquete", description="Tipo de dataset: marcajes_torniquete, asistencia, vehicular, academico, curricular, custom"),
    espacio_id: int = Query(1, description="ID del espacio institucional"),
    modo_solapamiento: str = Query("merge", description="'merge' (conserva previos e inserta nuevos) o 'overwrite' (reemplazo atómico de rango)"),
    clave_enlace: str = Query("rut", description="'rut', 'matricula' o 'crosswalk'"),
    modo_enlace: str = Query("tolerante", description="'tolerante' (asigna 'Sin carrera catalogada' si falta) o 'mandatorio' (aborta si <100%)"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("SuperAdmin", "Directivo", "Admin_Sistema", "Director_Recinto")),
):
    """
    Ejecuta el procesamiento definitivo bajo una sola transacción atómica en SQL Server.
    Soporta sobrescritura atómica de rango para recarga retroactiva enriquecida.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo no proporcionado")

    validar_acceso_espacio(espacio_id, current_user)

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El archivo subido se encuentra vacío")

    user_id = getattr(current_user, "id", current_user.get("id") if isinstance(current_user, dict) else None)

    try:
        return await ejecutar_ingesta_atomica(
            file_bytes=file_bytes,
            filename=file.filename,
            tipo=tipo,
            espacio_id=espacio_id,
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            db=db,
            usuario_id=user_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error durante la transacción de ingesta: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error durante la transacción de ingesta: {str(e)}",
        )


@router.post(
    "/retroactive-enrich",
    status_code=status.HTTP_200_OK,
    summary="Ejecutar enriquecimiento curricular retroactivo sobre eventos de asistencia (RF30)",
)
async def retroactive_enrich_endpoint(
    espacio_id: int = Query(1, description="ID del espacio institucional"),
    clave_enlace: str = Query("auto", description="Clave de enlace: 'auto', 'rut', 'matricula'"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_role("SuperAdmin", "Directivo", "Admin_Sistema", "Director_Recinto")),
):
    """
    Actualiza retroactivamente los eventos de asistencia que posean 'Sin carrera catalogada'
    cruzando en caliente con el catálogo institucional 'dim_estudiante_carrera' (RF30).
    """
    validar_acceso_espacio(espacio_id, current_user)
    return await enriquecer_asistencia_retroactiva(
        db=db,
        espacio_id=espacio_id,
        clave_enlace=clave_enlace,
    )


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    tipo: str = Query(..., description="asistencia, vehicular, academico, curricular, marcajes_torniquete, custom"),
    espacio_id: int = Query(..., description="ID del espacio institucional"),
    modo_solapamiento: str = Query("merge", description="'merge' o 'overwrite'"),
    clave_enlace: str = Query("rut", description="'rut', 'matricula' o 'crosswalk'"),
    modo_enlace: str = Query("tolerante", description="'tolerante' o 'mandatorio'"),
    file: UploadFile = File(...),
    current_user = Depends(require_role("SuperAdmin", "Directivo", "Admin_Sistema", "Director_Recinto")),
    db: AsyncSession = Depends(get_db)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo no encontrado")

    # 1. Validación de extensiones permitidas
    ext = Path(file.filename).suffix.lower()
    ext_permitidas = [e.strip().lower() for e in settings.EXTENSIONES_INGESTA_PERMITIDAS.split(",") if e.strip()]
    if ext not in ext_permitidas:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extensión '{ext}' no permitida. Formatos aceptados: {settings.EXTENSIONES_INGESTA_PERMITIDAS}",
        )

    validar_acceso_espacio(espacio_id, current_user)

    # 2. Almacenamiento en volumen y validación de tamaño máximo con streaming y SHA-256
    dir_ingesta = Path(settings.DIRECTORIO_INGESTA)
    dir_ingesta.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4()
    nombre_limpio = Path(file.filename).name.replace(" ", "_")
    ruta_temporal = dir_ingesta / f"temp_{job_id}_{nombre_limpio}"

    hasher = hashlib.sha256()
    total_bytes = 0
    limite_bytes = settings.TAMANO_MAXIMO_INGESTA_MB * 1024 * 1024

    try:
        with open(ruta_temporal, "wb") as f_out:
            while chunk := await file.read(1024 * 1024):  # 1 MB por chunk
                total_bytes += len(chunk)
                if total_bytes > limite_bytes:
                    f_out.close()
                    if ruta_temporal.exists():
                        ruta_temporal.unlink()
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"El archivo excede el tamaño máximo permitido de {settings.TAMANO_MAXIMO_INGESTA_MB} MB.",
                    )
                hasher.update(chunk)
                f_out.write(chunk)
    except HTTPException:
        raise
    except Exception as exc:
        if ruta_temporal.exists():
            ruta_temporal.unlink()
        raise HTTPException(status_code=500, detail=f"Error escribiendo archivo de ingesta: {exc}")

    if total_bytes == 0:
        if ruta_temporal.exists():
            ruta_temporal.unlink()
        raise HTTPException(status_code=400, detail="El archivo subido se encuentra vacío")

    sha256_hash = hasher.hexdigest()

    # 3. Rechazar duplicados preexistentes si no es modo overwrite
    if modo_solapamiento != "overwrite":
        stmt_dup = select(IngestionJob).where(
            IngestionJob.file_hash == sha256_hash,
            IngestionJob.estado == "completed",
        )
        res_dup = await db.execute(stmt_dup)
        duplicado = res_dup.scalars().first()
        if duplicado:
            if ruta_temporal.exists():
                ruta_temporal.unlink()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"El archivo con hash criptográfico {sha256_hash[:12]} ya fue procesado con éxito previamente ({duplicado.filename}). Para forzar reescritura seleccione modo 'overwrite'.",
            )

    # 4. Renombrar al archivo definitivo en volumen ingesta_archivos
    ruta_definitiva = dir_ingesta / f"{job_id}_{nombre_limpio}"
    ruta_temporal.rename(ruta_definitiva)

    # 5. Registrar el IngestionJob en base de datos con estado 'queued'
    user_id = getattr(current_user, "id", current_user.get("id") if isinstance(current_user, dict) else None)
    nuevo_job = IngestionJob(
        job_id=job_id,
        filename=file.filename,
        tipo=tipo,
        estado="queued",
        registros_ok=0,
        registros_error=0,
        creado_por=user_id,
        creado_en=datetime.now(timezone.utc),
        file_hash=sha256_hash,
        modo_solapamiento=modo_solapamiento,
        clave_enlace=clave_enlace,
        modo_enlace=modo_enlace,
        espacio_id=espacio_id,
    )
    db.add(nuevo_job)
    await db.commit()

    # 6. Ejecutar pipeline mediante tarea asíncrona con semáforo
    asyncio.create_task(
        encolar_y_procesar_ingesta(
            job_id=job_id,
            ruta_archivo=str(ruta_definitiva),
            tipo=tipo,
            espacio_id=espacio_id,
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
        )
    )

    return {
        "job_id": str(job_id),
        "status": "queued",
        "filename": file.filename,
        "file_hash": sha256_hash,
        "message": "Archivo recibido y encolado para procesamiento.",
    }


@router.get("/{job_id}/status")
async def get_job_status(job_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    job = await db.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
        
    return {
        "job_id": str(job.job_id),
        "estado": job.estado,
        "registros_ok": job.registros_ok,
        "registros_error": job.registros_error,
        "error_detail": job.error_detail
    }


@router.get("/history", response_model=List[IngestionHistoryItem])
async def get_ingestion_history(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    stmt = select(IngestionJob).order_by(IngestionJob.creado_en.desc()).limit(50)
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    return [
        IngestionHistoryItem(
            job_id=str(j.job_id),
            filename=j.filename,
            tipo=j.tipo,
            estado=j.estado,
            registros_ok=j.registros_ok,
            registros_error=j.registros_error,
            creado_en=j.creado_en,
            completado_en=j.completado_en,
            file_hash=j.file_hash,
            modo_solapamiento=j.modo_solapamiento,
            clave_enlace=j.clave_enlace,
            modo_enlace=j.modo_enlace,
            espacio_id=j.espacio_id,
            error_detail=j.error_detail
        )
        for j in jobs
    ]

