import logging
import re
import unicodedata
from datetime import datetime, date
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query, BackgroundTasks, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import require_permission, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.audit_service import record_download_audit
from app.schemas.excel_export_schemas import (
    SolicitudExportacionExcel,
    GraficoNativoPayload,
)
from app.services.excel_export_service import ExcelExportService

logger = logging.getLogger(__name__)
router = APIRouter()

TIPO_MIME_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def sanear_nombre_archivo_header(nombre: str) -> str:
    """Sanitiza el nombre de archivo a ASCII estricto para encabezados HTTP conformes a RFC."""
    normalizado = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode("ascii")
    limpio = re.sub(r"[^a-zA-Z0-9_.-]+", "_", normalizado).strip("_")
    return limpio or "reporte_excel"


@router.post(
    "/excel/grafico",
    summary="Exportar gráfico individual como objeto OpenXML nativo de Excel",
    response_class=Response,
)
async def exportar_grafico_individual_excel(
    payload: GraficoNativoPayload,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_permission("can_export")),
):
    """
    Genera un archivo Excel (.xlsx) con un gráfico OpenXML nativo (editable y vinculado a celdas).
    """
    try:
        solicitud = SolicitudExportacionExcel(
            modulo_nombre="Módulo Analítico UCT",
            periodo_label="Período Activo",
            filtros={},
            graficos=[payload],
        )
        contenido_excel = ExcelExportService.generar_excel_nativo(solicitud)
        nombre_limpio = sanear_nombre_archivo_header(payload.id)
        nombre_archivo = f"{nombre_limpio}_nativo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        client_ip = request.client.host if request.client else "127.0.0.1"
        background_tasks.add_task(
            record_download_audit,
            usuario_id=current_user.id,
            modulo="grafico_individual",
            formato="xlsx",
            filtro_detalle=f"Grafico ID: {payload.id}",
            ip_origen=client_ip,
        )

        return Response(
            content=contenido_excel,
            media_type=TIPO_MIME_EXCEL,
            headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar gráfico nativo de Excel: {str(exc)}",
        )


@router.post(
    "/excel/consolidado",
    summary="Exportar reporte consolidado multi-hoja con gráficos nativos OpenXML",
    response_class=Response,
)
async def exportar_consolidado_excel(
    solicitud: SolicitudExportacionExcel,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: Usuario = Depends(require_permission("can_export")),
):
    """
    Genera un único libro Excel (.xlsx) con:
    - Hoja de Resumen Ejecutivo con parámetros, filtros e índice.
    - Una hoja independiente por cada gráfico seleccionado conteniendo su objeto OpenXML nativo y tabla de celdas vinculada.
    """
    try:
        if not solicitud.graficos:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe incluir al menos un gráfico para exportar.",
            )

        contenido_excel = ExcelExportService.generar_excel_nativo(solicitud)
        mod_slug = sanear_nombre_archivo_header(solicitud.modulo_nombre).lower()
        nombre_archivo = f"Reporte_Consolidado_{mod_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        client_ip = request.client.host if request.client else "127.0.0.1"
        background_tasks.add_task(
            record_download_audit,
            usuario_id=current_user.id,
            modulo=mod_slug,
            formato="xlsx",
            filtro_detalle=f"Consolidado: {len(solicitud.graficos)} gráficos",
            ip_origen=client_ip,
        )

        return Response(
            content=contenido_excel,
            media_type=TIPO_MIME_EXCEL,
            headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error al compilar reporte consolidado de Excel: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar reporte consolidado de Excel: {str(exc)}",
        )


@router.get(
    "/excel/plantilla-salas-estudio",
    summary="Exportar reporte oficial institucional de salas de estudio en formato plantilla",
    response_class=Response,
)
async def exportar_plantilla_salas_estudio(
    request: Request,
    background_tasks: BackgroundTasks,
    espacio_id: int = Query(1, description="ID del espacio (1=Biblioteca)"),
    fecha_inicio: Optional[date] = Query(None, description="Fecha de inicio (YYYY-MM-DD)"),
    fecha_fin: Optional[date] = Query(None, description="Fecha de fin (YYYY-MM-DD)"),
    alcance: str = Query("conformes", description="Alcance de registros"),
    regimen_horario: Optional[str] = Query("todos"),
    direccion: Optional[str] = Query("todos"),
    dias_semana: Optional[str] = Query(None),
    door: Optional[str] = Query(None),
    carrera: Optional[str] = Query(None),
    facultad: Optional[str] = Query(None),
    periodo_label: Optional[str] = Query(None, description="Etiqueta visible del período"),
    current_user: Usuario = Depends(require_permission("can_export")),
    db: AsyncSession = Depends(get_db),
):
    """
    Genera el archivo Excel (.xlsx) con la plantilla oficial del 'Reporte Salas de Estudios'
    mostrando 4 tablas maestras vinculadas y 5 gráficos OpenXML nativos con tema oscuro.
    """
    validar_acceso_espacio(espacio_id, current_user)
    try:
        contenido_excel = await ExcelExportService.generar_reporte_plantilla_salas_estudio(
            session=db,
            espacio_id=espacio_id,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            alcance=alcance,
            regimen_horario=regimen_horario,
            direccion=direccion,
            dias_semana=dias_semana,
            door=door,
            carrera=carrera,
            facultad=facultad,
            periodo_label=periodo_label,
        )
        periodo_saneado = sanear_nombre_archivo_header(periodo_label or "Periodo")
        nombre_archivo = f"Reporte_Salas_Estudios_{periodo_saneado}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        client_ip = request.client.host if request.client else "127.0.0.1"
        background_tasks.add_task(
            record_download_audit,
            usuario_id=current_user.id,
            modulo="biblioteca_salas",
            formato="xlsx",
            filtro_fecha_inicio=str(fecha_inicio) if fecha_inicio else None,
            filtro_fecha_fin=str(fecha_fin) if fecha_fin else None,
            filtro_detalle=f"Plantilla Salas de Estudio - Período: {periodo_saneado}",
            ip_origen=client_ip,
        )

        return Response(
            content=contenido_excel,
            media_type=TIPO_MIME_EXCEL,
            headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar la plantilla oficial de salas de estudio: {str(exc)}",
        )

