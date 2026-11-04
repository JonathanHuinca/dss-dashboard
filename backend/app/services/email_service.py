import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("uvicorn.error")


def _construir_plantilla_base(contenido_cuerpo: str, titulo: str) -> str:
    """
    Estructura HTML base con identidad institucional de la Universidad Católica de Temuco.
    """
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{titulo}</title>
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


def _enviar_correo_sincrono(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
) -> bool:
    """
    Despacha un correo mediante conexión SMTP con cifrado STARTTLS.
    """
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning(
            "Servicio SMTP no configurado en settings. No se despachó el correo a %s.",
            destinatario,
        )
        return False

    remitente_formato = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL or settings.SMTP_USER}>"

    mensaje = MIMEMultipart("alternative")
    mensaje["Subject"] = asunto
    mensaje["From"] = remitente_formato
    mensaje["To"] = destinatario

    texto_alternativo = cuerpo_texto or "Por favor, visualice este mensaje en un cliente de correo con soporte HTML."
    mensaje.attach(MIMEText(texto_alternativo, "plain", "utf-8"))
    mensaje.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    try:
        servidor = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        servidor.ehlo()
        if settings.SMTP_USE_TLS:
            servidor.starttls()
            servidor.ehlo()
        servidor.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        servidor.sendmail(settings.SMTP_FROM_EMAIL or settings.SMTP_USER, [destinatario], mensaje.as_string())
        servidor.quit()
        logger.warning("Correo despachado exitosamente hacia: %s (Asunto: %s)", destinatario, asunto)
        return True
    except smtplib.SMTPAuthenticationError as err:
        logger.error("Error de autenticación SMTP al conectar con %s (código 535 Bad Credentials): %s", settings.SMTP_HOST, err)
        return False
    except smtplib.SMTPServerDisconnected as err:
        logger.error(
            "Servidor SMTP desconectó la sesión (535 Bad Credentials / Rechazo de credenciales por Google). "
            "Verifique que SMTP_USER sea el correo correcto y que SMTP_PASSWORD sea una contraseña de aplicación válida de 16 caracteres: %s",
            err,
        )
        return False
    except Exception as err:
        logger.error("Fallo inesperado al enviar correo SMTP a %s: %s", destinatario, err, exc_info=True)
        return False


async def enviar_correo_despacho(
    destinatario: str,
    asunto: str,
    cuerpo_html: str,
    cuerpo_texto: Optional[str] = None,
) -> bool:
    """
    Ejecuta el envío de correo de forma asíncrona sin bloquear el loop de eventos.
    """
    return await asyncio.to_thread(
        _enviar_correo_sincrono,
        destinatario=destinatario,
        asunto=asunto,
        cuerpo_html=cuerpo_html,
        cuerpo_texto=cuerpo_texto,
    )


async def enviar_correo_activacion(
    destinatario: str,
    nombre_destinatario: str,
    enlace_activacion: str,
) -> bool:
    """
    Genera y despacha el correo de invitación y activación de cuenta inicial.
    """
    asunto = "Activación de Cuenta — Plataforma DSS Campus San Francisco UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #002855; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_destinatario or destinatario}:
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
    asunto = "Recuperación de Contraseña — Plataforma DSS Campus San Francisco UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #002855; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_destinatario or destinatario}:
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
    asunto = "Alta de Cuenta Consultor de Reportes Ejecutivos — DSS UCT"
    cuerpo_interno = f"""
        <h2 style="margin-top: 0; color: #003865; font-size: 18px; font-weight: 700;">
            Estimado/a {nombre_destinatario or destinatario}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Se ha habilitado su perfil de <strong>Consultor de Reportes Ejecutivos</strong> en el Sistema de Apoyo a la Toma de Decisiones (DSS) del Campus San Francisco — Universidad Católica de Temuco.
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border-left: 4px solid #C59B27; border-radius: 6px; padding: 14px 18px; margin: 18px 0;">
            <tr>
                <td style="font-size: 13px; color: #1e293b; line-height: 1.5;">
                    <strong>Titular:</strong> {nombre_destinatario}<br>
                    <strong>Cargo:</strong> {cargo}<br>
                    <strong>Unidad / Carrera:</strong> {unidad_academica}<br>
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
    asunto = f"Reporte Ejecutivo Disponible ({codigo_corto}) — {titulo_reporte}"
    bloque_nota = ""
    if nota_general and nota_general.strip():
        bloque_nota = f"""
        <div style="background-color: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #C59B27; border-radius: 6px; padding: 12px 16px; margin: 16px 0; font-size: 13px; color: #1e293b;">
            <strong style="color: #92400e; display: block; margin-bottom: 4px;">Nota Ejecutiva del Emisor:</strong>
            {nota_general}
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
            Estimado/a {nombre_destinatario or destinatario}:
        </h2>
        <p style="color: #334155; font-size: 14px;">
            Se ha habilitado y puesto a su disposición un nuevo <strong>Reporte Ejecutivo Institucional</strong> en el Sistema DSS del Campus San Francisco — Universidad Católica de Temuco.
        </p>
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #003865; border-radius: 6px; padding: 16px 18px; margin: 18px 0;">
            <tr>
                <td style="font-size: 13px; color: #1e293b; line-height: 1.6;">
                    <strong>Código Oficial:</strong> {codigo_corto}<br>
                    <strong>Título del Reporte:</strong> {titulo_reporte}<br>
                    <strong>Módulo / Recinto:</strong> {espacio_nombre}<br>
                    <strong>Período Analizado:</strong> {periodo_texto}<br>
                    <strong>Destinatario:</strong> {nombre_destinatario} ({cargo} — {unidad_academica})<br>
                    <strong>Finalidad:</strong> {finalidad_reporte}
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
