from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, validar_acceso_espacio
from app.domain.auth_models import Usuario
from app.services.auth_service import normalizar_rol
from app.services.servicio_reportes_compartidos import ServicioReportesCompartidos

router = APIRouter()


def verificar_permiso_compartir_reportes(
    current_user: Usuario = Depends(get_current_user),
) -> Usuario:
    """
    Permite gestionar reportes compartidos a todos los roles institucionales
    EXCEPTO Guardia_Seguridad y Consultor_Reporte.
    """
    roles_normalizados = {normalizar_rol(r.nombre) for r in current_user.roles}
    roles_restringidos = {"Guardia_Seguridad", "Consultor_Reporte"}
    if not roles_normalizados or roles_normalizados.issubset(roles_restringidos):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su rol no está autorizado para emitir ni administrar reportes compartidos.",
        )
    return current_user


class RegistrarConsultorReporteRequest(BaseModel):
    nombre_completo: str = Field(..., min_length=2)
    email: str = Field(..., min_length=3)
    cargo: str = Field(..., min_length=2)
    unidad_academica: str = Field(..., min_length=2)


class NotaItemSchema(BaseModel):
    id: str = Field(..., description="Identificador único o clave de gráfico/sección")
    seccion: str = Field("general", description="general o id del gráfico asociado")
    titulo: str = Field("", description="Título breve de la nota")
    contenido: str = Field(..., description="Texto de la observación o nota del emisor")
    autor: Optional[str] = None
    fecha: Optional[str] = None


class CrearReporteCompartidoRequest(BaseModel):
    espacio_id: int = Field(..., description="1=Biblioteca CSF, 2=Estacionamiento CSF")
    destinatario_nombre: str = Field(..., min_length=2)
    destinatario_email: str = Field(..., min_length=3)
    destinatario_cargo: str = Field(..., min_length=2)
    destinatario_unidad: str = Field(..., min_length=2)
    titulo_reporte: str = Field(..., min_length=3)
    finalidad_reporte: str = Field(..., min_length=3)
    nota_general: Optional[str] = Field(None)
    notas_items: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    fecha_inicio: str = Field(..., description="YYYY-MM-DD")
    fecha_fin: str = Field(..., description="YYYY-MM-DD")
    modo_datos: str = Field("dinamico_acotado", description="dinamico_acotado | instantanea_fija")
    filtros_bloqueados: Dict[str, Any] = Field(default_factory=dict)
    graficos_visibles: List[str] = Field(default_factory=list)
    indicadores_visibles: List[str] = Field(default_factory=list)
    permitir_exportacion: bool = Field(True)
    permitir_ia: bool = Field(False, description="IA deshabilitada por defecto para el destinatario")
    expira_en: Optional[str] = Field(None, description="Fecha/hora ISO de expiración o null para indefinido")


class ActualizarReporteCompartidoRequest(BaseModel):
    activo: Optional[bool] = None
    permitir_ia: Optional[bool] = None
    permitir_exportacion: Optional[bool] = None
    titulo_reporte: Optional[str] = None
    finalidad_reporte: Optional[str] = None
    nota_general: Optional[str] = None
    notas_items: Optional[List[Dict[str, Any]]] = None
    graficos_visibles: Optional[List[str]] = None
    indicadores_visibles: Optional[List[str]] = None
    expira_en: Optional[str] = None
    reenviar_correo: Optional[bool] = None


class ActualizarDestinatarioEstadoRequest(BaseModel):
    activo: bool


class ConsultaIAReporteRequest(BaseModel):
    pregunta: str = Field(..., min_length=2, max_length=1200)


@router.get("/mis-reportes", summary="Bandeja histórica de reportes del usuario Consultor_Reporte autenticado")
async def obtener_mis_reportes(
    current_user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.obtener_mis_reportes_consultor(
        session=db,
        usuario_actual=current_user,
    )


@router.post("/consultores", status_code=status.HTTP_201_CREATED, summary="Crear cuenta de usuario Consultor_Reporte y enviar invitación de contraseña")
async def registrar_consultor_reporte(
    payload: RegistrarConsultorReporteRequest,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.registrar_consultor_reporte(
        session=db,
        usuario_actual=current_user,
        payload=payload.model_dump(),
    )


@router.get("", summary="Listar reportes ejecutivos emitidos y destinatarios")
async def listar_reportes_compartidos(
    espacio_id: Optional[int] = Query(None),
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    if espacio_id is not None:
        validar_acceso_espacio(espacio_id, current_user)
    return await ServicioReportesCompartidos.listar_reportes_emitidos(
        session=db,
        usuario_actual=current_user,
        espacio_id=espacio_id,
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear enlace de reporte ejecutivo compartido")
async def crear_reporte_compartido(
    payload: CrearReporteCompartidoRequest,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    validar_acceso_espacio(payload.espacio_id, current_user)
    return await ServicioReportesCompartidos.crear_reporte_compartido(
        session=db,
        usuario_actual=current_user,
        payload=payload.model_dump(),
    )


@router.patch("/{reporte_id}", summary="Habilitar/deshabilitar reporte, IA, notas, gráficos o vigencia")
async def actualizar_reporte_compartido(
    reporte_id: str,
    payload: ActualizarReporteCompartidoRequest,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.actualizar_estado_y_configuracion_reporte(
        session=db,
        usuario_actual=current_user,
        reporte_id=reporte_id,
        payload=payload.model_dump(exclude_unset=True),
    )


@router.delete("/{reporte_id}", summary="Eliminar reporte compartido")
async def eliminar_reporte_compartido(
    reporte_id: str,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.eliminar_reporte_compartido(
        session=db,
        usuario_actual=current_user,
        reporte_id=reporte_id,
    )


@router.patch("/destinatarios/{destinatario_id}", summary="Habilitar o deshabilitar cuenta de destinatario")
async def actualizar_estado_destinatario(
    destinatario_id: int,
    payload: ActualizarDestinatarioEstadoRequest,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.actualizar_estado_destinatario(
        session=db,
        destinatario_id=destinatario_id,
        activo=payload.activo,
    )


@router.delete("/destinatarios/{destinatario_id}", summary="Eliminar usuario Consultor de Reportes y sus reportes asociados")
async def eliminar_destinatario_consultor(
    destinatario_id: int,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.eliminar_destinatario_consultor(
        session=db,
        usuario_actual=current_user,
        destinatario_id=destinatario_id,
    )


# ---------------------------------------------------------------------------
# Endpoints públicos confinados por token criptográfico (para el destinatario)
# ---------------------------------------------------------------------------
@router.get("/publico/{token_acceso}", summary="Obtener datos confinados de un reporte compartido por token")
async def obtener_reporte_publico(
    token_acceso: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_origen = request.client.host if request.client else None
    return await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
        session=db,
        token_acceso=token_acceso,
        ip_origen=ip_origen,
    )


@router.get("/portal/{token_portal}", summary="Obtener bandeja histórica de reportes del destinatario")
async def obtener_portal_destinatario(
    token_portal: str,
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.obtener_portal_destinatario_por_token(
        session=db,
        token_portal=token_portal,
    )


@router.post("/publico/{token_acceso}/consultar-ia", summary="Consultar IA confinada al reporte (si está habilitada)")
async def consultar_ia_reporte_publico(
    token_acceso: str,
    payload: ConsultaIAReporteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_origen = request.client.host if request.client else None
    return await ServicioReportesCompartidos.consultar_ia_reporte_confinado(
        session=db,
        token_acceso=token_acceso,
        pregunta=payload.pregunta,
        ip_origen=ip_origen,
    )

