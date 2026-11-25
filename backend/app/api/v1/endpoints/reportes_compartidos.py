from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles, validar_acceso_espacio
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


class VincularUsuarioExistenteRequest(BaseModel):
    usuario_id: int = Field(..., gt=0)
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
    sesion_id: Optional[str] = Field("principal", max_length=64)


class EventoReportePublicoRequest(BaseModel):
    accion: str = Field(..., description="descarga_excel | descarga_csv | descarga_pdf | descarga_imagen")
    detalle: Optional[str] = Field(None, max_length=500)


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


@router.get("/usuarios-candidatos", summary="Listar usuarios institucionales activos candidatos para rol Consultor_Reporte")
async def obtener_usuarios_candidatos(
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.obtener_usuarios_candidatos_consultor(
        session=db,
    )


@router.post("/vincular-usuario-existente", status_code=status.HTTP_201_CREATED, summary="Vincular usuario del campus a rol Consultor_Reporte preservando su contraseña")
async def vincular_usuario_existente(
    payload: VincularUsuarioExistenteRequest,
    current_user: Usuario = Depends(verificar_permiso_compartir_reportes),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.vincular_usuario_existente_consultor(
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


@router.get("/auditoria", summary="Auditoría gerencial de reportes compartidos y actividad del destinatario")
async def obtener_auditoria_reportes(
    espacio_id: Optional[int] = Query(None),
    emisor_rol: Optional[str] = Query(None, description="directivo | analista | admin"),
    estado_revision: Optional[str] = Query(None, description="revisado | sin_revisar"),
    solo_activos: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: Usuario = Depends(require_roles(["Admin_Sistema", "Director_Recinto"])),
    db: AsyncSession = Depends(get_db),
):
    if espacio_id is not None:
        validar_acceso_espacio(espacio_id, current_user)
    return await ServicioReportesCompartidos.obtener_auditoria_reportes_emitidos(
        session=db,
        usuario_actual=current_user,
        espacio_id=espacio_id,
        emisor_rol=emisor_rol,
        estado_revision=estado_revision,
        solo_activos=solo_activos,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{reporte_id}/eventos", summary="Timeline cronológico de aperturas, descargas e IA de un reporte")
async def obtener_eventos_reporte(
    reporte_id: str,
    accion: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=500),
    current_user: Usuario = Depends(require_roles(["Admin_Sistema", "Director_Recinto"])),
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.obtener_eventos_reporte(
        session=db,
        usuario_actual=current_user,
        reporte_id=reporte_id,
        accion=accion,
        limit=limit,
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
    user_agent = request.headers.get("user-agent")
    return await ServicioReportesCompartidos.obtener_reporte_publico_por_token(
        session=db,
        token_acceso=token_acceso,
        ip_origen=ip_origen,
        user_agent=user_agent,
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


@router.post("/publico/{token_acceso}/evento", summary="Registrar evento de descarga o exportación desde reporte compartido")
async def registrar_evento_reporte_publico(
    token_acceso: str,
    payload: EventoReportePublicoRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_origen = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await ServicioReportesCompartidos.registrar_evento_reporte_publico(
        session=db,
        token_acceso=token_acceso,
        accion=payload.accion,
        detalle=payload.detalle,
        ip_origen=ip_origen,
        user_agent=user_agent,
    )


@router.get("/publico/{token_acceso}/ia/historial", summary="Obtener historial de chat IA persistido del reporte compartido")
async def obtener_historial_ia_reporte_publico(
    token_acceso: str,
    db: AsyncSession = Depends(get_db),
):
    return await ServicioReportesCompartidos.obtener_historial_ia_reporte_publico(
        session=db,
        token_acceso=token_acceso,
    )


@router.post("/publico/{token_acceso}/consultar-ia", summary="Consultar IA confinada al reporte (si está habilitada)")
async def consultar_ia_reporte_publico(
    token_acceso: str,
    payload: ConsultaIAReporteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip_origen = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return await ServicioReportesCompartidos.consultar_ia_reporte_confinado(
        session=db,
        token_acceso=token_acceso,
        pregunta=payload.pregunta,
        sesion_id=payload.sesion_id or "principal",
        ip_origen=ip_origen,
        user_agent=user_agent,
    )

