import asyncio
import html
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, Tuple
from cachetools import TTLCache
from sqlalchemy import desc, select

from app.core.config import settings, obtener_url_frontend
from app.core.database import AsyncSessionLocal
from app.core.security_cipher import decrypt_api_key
from app.core.validacion_red import sanitizar_error_credencial
from app.domain.config_models import ConfiguracionSMTP

logger = logging.getLogger("uvicorn.error")
_cache_smtp_activo: TTLCache = TTLCache(maxsize=1, ttl=60)


def limpiar_cache_smtp() -> None:
    """Invalida la configuración SMTP cacheada tras altas, activaciones o eliminaciones."""
    _cache_smtp_activo.clear()


async def obtener_config_smtp_activa() -> Optional[Dict[str, Any]]:
    """Obtiene la cuenta SMTP activa desde BD (Fernet) o fallback .env."""
    if "activo" in _cache_smtp_activo:
        return _cache_smtp_activo["activo"]

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(ConfiguracionSMTP)
                .where(ConfiguracionSMTP.es_activa == True)
                .order_by(desc(ConfiguracionSMTP.updated_at), desc(ConfiguracionSMTP.id))
                .limit(1)
            )
            cfg = (await db.execute(stmt)).scalar_one_or_none()
            if cfg:
                password = decrypt_api_key(cfg.encrypted_password)
                datos = {
                    "host": cfg.host,
                    "port": int(cfg.port),
                    "use_tls": bool(cfg.use_tls),
                    "use_ssl": bool(cfg.use_ssl),
                    "username": cfg.username,
                    "password": password,
                    "from_email": cfg.from_email,
                    "from_name": cfg.from_name,
                    "origen": "db",
                    "nombre": cfg.nombre,
                }
                _cache_smtp_activo["activo"] = datos
                return datos
    except Exception as exc:
        logger.debug("Lectura de configuracion_smtp omitida: %s", sanitizar_error_credencial(exc))

    if settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
        datos_env = {
            "host": settings.SMTP_HOST,
            "port": int(settings.SMTP_PORT),
            "use_tls": bool(settings.SMTP_USE_TLS),
            "use_ssl": int(settings.SMTP_PORT) == 465,
            "username": settings.SMTP_USER,
            "password": settings.SMTP_PASSWORD,
            "from_email": settings.SMTP_FROM_EMAIL or settings.SMTP_USER,
            "from_name": settings.SMTP_FROM_NAME,
            "origen": "env",
            "nombre": "Respaldo .env",
        }
        _cache_smtp_activo["activo"] = datos_env
        return datos_env

    return None


def _normalizar_enlace_frontend(enlace: Optional[str]) -> str:
    if not enlace:
        return ""
    base_actual = obtener_url_frontend()
    if enlace.startswith("/"):
        return f"{base_actual}{enlace}"
    if enlace.startswith("http://localhost:3000") and base_actual != "http://localhost:3000":
        return enlace.replace("http://localhost:3000", base_actual, 1)
    return enlace


def _construir_plantilla_base(contenido_cuerpo: str, titulo: str) -> str:
    """
    Estructura HTML base con identidad institucional de la Universidad Católica de Temuco.
    """
    titulo_html = html.escape(titulo or "", quote=True)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titulo_html}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 30px 10px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 600px; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
                    <!-- Cabecera Institucional UCT -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #002855 0%, #0056b3 100%); padding: 28px 32px; text-align: left;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 20px; font-weight: 700; letter-spacing: 0.5px;">
                                SISTEMA DSS — CAMPUS SAN FRANCISCO
                            </h1>
                            <p style="margin: 4px 0 0 0; color: #93c5fd; font-size: 13px; font-weight: 500;">
                                Universidad Católica de Temuco
                            </p>
                        </td>
                    </tr>
                    <!-- Contenido Central -->
                    <tr>
                        <td style="padding: 36px 32px 28px 32px; line-height: 1.6;">
                            {contenido_cuerpo}
                        </td>
                    </tr>
                    <!-- Pie de Página Institucional -->
                    <tr>
                        <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 32px; text-align: center; font-size: 12px; color: #64748b;">
                            <p style="margin: 0 0 6px 0;">Este es un mensaje institucional generado automáticamente por la plataforma DSS.</p>
                            <p style="margin: 0;">Campus San Francisco, Universidad Católica de Temuco — Por favor, no responda a este correo.</p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""


def _enviar_correo_sincrono_detallado(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
    smtp_cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Despacha un correo mediante SMTP (STARTTLS o SSL) retornando estado y detalle sanitizado."""
    cfg = smtp_cfg
    if cfg is None and settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD:
        cfg = {
            "host": settings.SMTP_HOST,
            "port": int(settings.SMTP_PORT),
            "use_tls": bool(settings.SMTP_USE_TLS),
            "use_ssl": int(settings.SMTP_PORT) == 465,
            "username": settings.SMTP_USER,
            "password": settings.SMTP_PASSWORD,
            "from_email": settings.SMTP_FROM_EMAIL or settings.SMTP_USER,
            "from_name": settings.SMTP_FROM_NAME,
        }

    if not cfg or not cfg.get("host") or not cfg.get("username") or not cfg.get("password"):
        logger.warning("Servicio SMTP no configurado. No se despachó el correo a %s.", destinatario)
        return False, "No existe un servidor SMTP activo configurado."

    host = str(cfg["host"])
    port = int(cfg["port"])
    username = str(cfg["username"])
    password = str(cfg["password"])
    from_email = str(cfg.get("from_email") or username)
    from_name = str(cfg.get("from_name") or settings.SMTP_FROM_NAME)
    use_ssl = bool(cfg.get("use_ssl", False))
    use_tls = bool(cfg.get("use_tls", True))

    remitente_formato = f"{from_name} <{from_email}>"

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = remitente_formato
    mensaje["To"] = destinatario

    texto_alternativo = cuerpo_texto or "Por favor, visualice este mensaje en un cliente de correo con soporte HTML."
    mensaje.attach(MIMEText(texto_alternativo, "plain", "utf-8"))
    mensaje.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=15) as servidor:
                servidor.ehlo()
                servidor.login(username, password)
                servidor.sendmail(from_email, [destinatario], mensaje.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as servidor:
                servidor.ehlo()
                if use_tls:
                    servidor.starttls()
                    servidor.ehlo()
                servidor.login(username, password)
                servidor.sendmail(from_email, [destinatario], mensaje.as_string())
        logger.warning("Correo despachado exitosamente hacia: %s (Asunto: %s)", destinatario, asunto)
        return True, f"Correo de prueba enviado correctamente a {destinatario}."
    except smtplib.SMTPAuthenticationError as err:
        detalle = sanitizar_error_credencial(err, password)
        logger.error("Error de autenticación SMTP al conectar con %s: %s", host, detalle)
        return False, f"Error de autenticación SMTP: {detalle}"
    except smtplib.SMTPServerDisconnected as err:
        detalle = sanitizar_error_credencial(err, password)
        logger.error("Servidor SMTP %s desconectó la sesión: %s", host, detalle)
        return False, f"Conexión cerrada por el servidor SMTP: {detalle}"
    except Exception as err:
        detalle = sanitizar_error_credencial(err, password)
        logger.error("Fallo inesperado al enviar correo SMTP a %s: %s", destinatario, detalle)
        return False, f"Error enviando correo SMTP: {detalle}"


def _enviar_correo_sincrono(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
    smtp_cfg: Optional[Dict[str, Any]] = None,
) -> bool:
    ok, _ = _enviar_correo_sincrono_detallado(
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        smtp_cfg=smtp_cfg,
    )
    return ok


async def enviar_correo_despacho(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
) -> bool:
    """Ejecuta el envío de correo de forma asíncrona sin bloquear el loop de eventos."""
    smtp_cfg = await obtener_config_smtp_activa()
    return await asyncio.to_thread(
        _enviar_correo_sincrono,
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
        smtp_cfg=smtp_cfg,
    )


async def probar_envio_smtp(smtp_cfg: Dict[str, Any], destinatario: str) -> Tuple[bool, str]:
    """Envía un correo de verificación técnica para validar credenciales SMTP sin guardar logs secretos."""
    asunto = "Verificación de Servidor SMTP — Plataforma DSS UCT"
    nombre_perfil = html.escape(str(smtp_cfg.get("nombre", "Configurado")), quote=True)
    host_seguro = html.escape(str(smtp_cfg.get("host", "")), quote=True)
    port_seguro = html.escape(str(smtp_cfg.get("port", "")), quote=True)
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #002855; font-size: 18px; font-weight: 700;">
            Prueba de Conectividad SMTP Exitosa
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Este mensaje confirma que el perfil SMTP <strong>{nombre_perfil}</strong>
            (<code>{host_seguro}:{port_seguro}</code>) está operativo y autorizado para
            despachar notificaciones de activación y reportes ejecutivos desde el DSS UCT.
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await asyncio.to_thread(
        _enviar_correo_sincrono_detallado,
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=plantilla_html,
        cuerpo_texto="Prueba de conectividad SMTP exitosa para la plataforma DSS UCT.",
        smtp_cfg=smtp_cfg,
    )


async def enviar_correo_activacion(
    destinatario: str,
    nombre_destinatario: str,
    enlace_activacion: str,
) -> bool:
    """
    Genera y despacha el correo de invitación y activación de cuenta inicial.
    """
    enlace_activacion = html.escape(_normalizar_enlace_frontend(enlace_activacion), quote=True)
    nombre_seguro = html.escape(nombre_destinatario or destinatario, quote=True)
    asunto = "Activación de Cuenta — Plataforma DSS Campus San Francisco UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #002855; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_seguro}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Ha sido registrado como usuario en el <strong>Sistema de Apoyo a la Toma de Decisiones (DSS)</strong> del Campus San Francisco de la Universidad Católica de Temuco.
        </p>
        <p style="color: #334155; font-size: 14px;">
            Para habilitar su acceso y establecer su contraseña por primera vez de forma segura, presione el siguiente botón:
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{enlace_activacion}" style="background-color: #0056b3; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block; box-shadow: 0 2px 4px rgba(0,86,179,0.3);">
                Activar Cuenta y Definir Contraseña
            </a>
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 24px;">
            Este enlace es de uso único y tiene una validez estricta de <strong>1 hora</strong> por motivos de seguridad institucional (OWASP ASVS).
        </p>
        <p style="color: #94a3b8; font-size: 11px; word-break: break-all;">
            Si el botón no funciona, copie y pegue la siguiente dirección en su navegador:<br>
            <a href="{enlace_activacion}" style="color: #0056b3;">{enlace_activacion}</a>
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await enviar_correo_despacho(destinatario, asunto, plantilla_html)


async def enviar_correo_recuperacion(
    destinatario: str,
    nombre_destinatario: str,
    enlace_recuperacion: str,
) -> bool:
    """
    Genera y despacha el correo de recuperación y desbloqueo de contraseña.
    """
    enlace_recuperacion = html.escape(_normalizar_enlace_frontend(enlace_recuperacion), quote=True)
    nombre_seguro = html.escape(nombre_destinatario or destinatario, quote=True)
    asunto = "Recuperación de Contraseña — Plataforma DSS Campus San Francisco UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #002855; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_seguro}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Hemos recibido una solicitud para restablecer la contraseña de su cuenta en la plataforma <strong>DSS UCT</strong>.
        </p>
        <p style="color: #334155; font-size: 14px;">
            Para definir una nueva credencial y desbloquear su cuenta de forma autónoma, haga clic en el botón a continuación:
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{enlace_recuperacion}" style="background-color: #0056b3; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block; box-shadow: 0 2px 4px rgba(0,86,179,0.3);">
                Restablecer Contraseña
            </a>
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 24px;">
            Por motivos de seguridad (Directriz OWASP ASVS), este enlace expirará en <strong>15 minutos</strong> y solo puede ser utilizado una única vez.
        </p>
        <p style="color: #94a3b8; font-size: 11px;">
            Si usted no realizó esta solicitud, puede desestimar este mensaje. Su cuenta permanecerá protegida.
        </p>
        <p style="color: #94a3b8; font-size: 11px; word-break: break-all;">
            Enlace alternativo:<br>
            <a href="{enlace_recuperacion}" style="color: #0056b3;">{enlace_recuperacion}</a>
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await enviar_correo_despacho(destinatario, asunto, plantilla_html)


async def enviar_correo_bloqueo_login(
    destinatario: str,
    nombre_destinatario: str,
    enlace_recuperacion: str,
    intentos: int = 5,
) -> bool:
    """Notifica bloqueo preventivo tras intentos fallidos consecutivos con enlace de restablecimiento."""
    enlace_recuperacion = html.escape(_normalizar_enlace_frontend(enlace_recuperacion), quote=True)
    nombre_seguro = html.escape(nombre_destinatario or destinatario, quote=True)
    asunto = "Alerta de Seguridad: Cuenta Bloqueada — Plataforma DSS Campus San Francisco UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #991b1b; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_seguro}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Se detectaron <strong>{int(intentos)} intentos fallidos consecutivos</strong> al ingresar la contraseña de su cuenta en el <strong>Sistema DSS Campus San Francisco UCT</strong>.
        </p>
        <p style="color: #334155; font-size: 14px;">
            Como medida preventiva de seguridad, su cuenta fue bloqueada temporalmente por <strong>15 minutos</strong>. Si necesita recuperar el acceso de inmediato o no reconoce estos intentos, puede restablecer su contraseña y desbloquear su cuenta desde el siguiente botón:
        </p>
        <div style="text-align: center; margin: 32px 0;">
            <a href="{enlace_recuperacion}" style="background-color: #b91c1c; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 14px; display: inline-block; box-shadow: 0 2px 4px rgba(185,28,28,0.28);">
                Restablecer Contraseña y Desbloquear
            </a>
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 24px;">
            Por seguridad (OWASP ASVS), este enlace expira en <strong>15 minutos</strong> y es de uso único. También se notificó al Administrador del Sistema sobre este evento.
        </p>
        <p style="color: #94a3b8; font-size: 11px; word-break: break-all;">
            Enlace alternativo:<br>
            <a href="{enlace_recuperacion}" style="color: #0056b3;">{enlace_recuperacion}</a>
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await enviar_correo_despacho(destinatario, asunto, plantilla_html)


async def enviar_correo_activacion_consultor(
    destinatario: str,
    nombre_destinatario: str,
    cargo: str,
    unidad_academica: str,
    enlace_activacion: str,
    enlace_portal: str,
) -> bool:
    """
    Despacha el correo institucional UCT para que el nuevo usuario Consultor_Reporte
    active su cuenta y defina su contraseña de acceso a su bandeja de reportes ejecutivos.
    """
    enlace_activacion = html.escape(_normalizar_enlace_frontend(enlace_activacion), quote=True)
    enlace_portal = html.escape(_normalizar_enlace_frontend(enlace_portal), quote=True)
    nombre_seguro = html.escape(nombre_destinatario or destinatario, quote=True)
    titular_seguro = html.escape(nombre_destinatario or "", quote=True)
    cargo_seguro = html.escape(cargo or "", quote=True)
    unidad_segura = html.escape(unidad_academica or "", quote=True)
    asunto = "Alta de Cuenta Consultor de Reportes Ejecutivos — DSS UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #003865; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_seguro}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Se ha habilitado su perfil de <strong>Consultor de Reportes Ejecutivos</strong> en el Sistema de Apoyo a la Toma de Decisiones (DSS) del Campus San Francisco — Universidad Católica de Temuco.
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-left: 4px solid #C59B27; border-radius: 6px; padding: 14px 18px; margin: 18px 0;">
            <tr>
                <td style="font-size: 13px; color: #1e293b; line-height: 1.5;">
                    <strong>Titular:</strong> {titular_seguro}<br>
                    <strong>Cargo:</strong> {cargo_seguro}<br>
                    <strong>Unidad / Carrera:</strong> {unidad_segura}<br>
                    <strong>Rol Asignado:</strong> Consultor de Reportes Ejecutivos (Acceso confinado a reportes emitidos)
                </td>
            </tr>
        </table>
        <p style="color: #334155; font-size: 14px;">
            Para crear su contraseña personal y acceder a su bandeja histórica de reportes ejecutivos, presione el siguiente botón institucional:
        </p>
        <div style="text-align: center; margin: 28px 0;">
            <a href="{enlace_activacion}" style="background-color: #003865; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block; border-bottom: 3px solid #C59B27;">
                Crear Contraseña y Activar Cuenta Consultor
            </a>
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 16px;">
            Una vez definida su contraseña, podrá iniciar sesión en el portal institucional o consultar directamente su bandeja histórica en:<br>
            <a href="{enlace_portal}" style="color: #003865; font-weight: 600;">{enlace_portal}</a>
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await enviar_correo_despacho(destinatario, asunto, plantilla_html)


async def enviar_correo_reporte_ejecutivo(
    destinatario: str,
    nombre_destinatario: str,
    cargo: str,
    unidad_academica: str,
    titulo_reporte: str,
    codigo_corto: str,
    espacio_nombre: str,
    periodo_texto: str,
    finalidad_reporte: str,
    nota_general: Optional[str],
    enlace_reporte: str,
    enlace_portal: str,
    enlace_activacion_pendiente: Optional[str] = None,
) -> bool:
    """
    Despacha el correo institucional UCT notificando la emisión o habilitación de un Reporte Ejecutivo Compartido.
    """
    enlace_reporte = html.escape(_normalizar_enlace_frontend(enlace_reporte), quote=True)
    enlace_portal = html.escape(_normalizar_enlace_frontend(enlace_portal), quote=True)
    if enlace_activacion_pendiente:
        enlace_activacion_pendiente = html.escape(_normalizar_enlace_frontend(enlace_activacion_pendiente), quote=True)

    nombre_seguro = html.escape(nombre_destinatario or destinatario, quote=True)
    titular_seguro = html.escape(nombre_destinatario or "", quote=True)
    cargo_seguro = html.escape(cargo or "", quote=True)
    unidad_segura = html.escape(unidad_academica or "", quote=True)
    titulo_seguro = html.escape(titulo_reporte or "", quote=True)
    codigo_seguro = html.escape(codigo_corto or "", quote=True)
    espacio_seguro = html.escape(espacio_nombre or "", quote=True)
    periodo_seguro = html.escape(periodo_texto or "", quote=True)
    finalidad_segura = html.escape(finalidad_reporte or "", quote=True)

    asunto = f"Reporte Ejecutivo Disponible ({codigo_corto}) — {titulo_reporte}"
    bloque_nota = ""
    if nota_general and nota_general.strip():
        nota_segura = html.escape(nota_general.strip(), quote=True).replace("\n", "<br>")
        bloque_nota = f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #C59B27; border-radius: 6px; padding: 12px 16px; margin: 16px 0; font-size: 13px; color: #1e293b;">
            <strong style="color: #92400e; display: block; margin-bottom: 4px;">Nota Ejecutiva del Emisor:</strong>
            {nota_segura}
        </div>
        """

    bloque_activacion = ""
    if enlace_activacion_pendiente:
        bloque_activacion = f"""
        <div style="background-color: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; padding: 14px 16px; margin: 20px 0; font-size: 13px; color: #0c4a6e;">
            <strong>Importante — Activación de Contraseña Pendiente:</strong><br>
            Su cuenta de Consultor de Reportes aún no tiene una contraseña configurada. Primero cree su contraseña en el siguiente enlace para habilitar su cuenta:<br>
            <div style="margin-top: 10px;">
                <a href="{enlace_activacion_pendiente}" style="background-color: #C59B27; color: #003865; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-weight: 700; font-size: 12px; display: inline-block;">
                    Crear mi Contraseña de Consultor
                </a>
            </div>
        </div>
        """

    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #003865; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_seguro}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Se ha habilitado y puesto a su disposición un nuevo <strong>Reporte Ejecutivo Institucional</strong> en el Sistema DSS del Campus San Francisco — Universidad Católica de Temuco.
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #003865; border-radius: 6px; padding: 16px 18px; margin: 18px 0;">
            <tr>
                <td style="font-size: 13px; color: #1e293b; line-height: 1.6;">
                    <strong>Código Oficial:</strong> {codigo_seguro}<br>
                    <strong>Título del Reporte:</strong> {titulo_seguro}<br>
                    <strong>Módulo / Recinto:</strong> {espacio_seguro}<br>
                    <strong>Período Analizado:</strong> {periodo_seguro}<br>
                    <strong>Destinatario:</strong> {titular_seguro} ({cargo_seguro} — {unidad_segura})<br>
                    <strong>Finalidad:</strong> {finalidad_segura}
                </td>
            </tr>
        </table>
        {bloque_nota}
        {bloque_activacion}
        <div style="text-align: center; margin: 28px 0;">
            <a href="{enlace_reporte}" style="background-color: #003865; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; display: inline-block; border-bottom: 3px solid #C59B27;">
                Abrir Reporte Ejecutivo Institucional
            </a>
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 16px;">
            También puede revisar el historial completo de todos los reportes emitidos a su nombre ingresando con su cuenta o mediante su bandeja histórica:<br>
            <a href="{enlace_portal}" style="color: #003865; font-weight: 600;">{enlace_portal}</a>
        </p>
    """
    plantilla_html = _construir_plantilla_base(cuerpo_interno, asunto)
    return await enviar_correo_despacho(destinatario, asunto, plantilla_html)
