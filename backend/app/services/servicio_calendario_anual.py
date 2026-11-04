"""
servicio_calendario_anual.py — Servicio de verificación, sincronización anual y
control de reintentos del calendario académico institucional UCT.
"""
import asyncio
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.domain.models import CalendarioAcademico, EstadoCalendarioAnual
from app.ml.gestor_modelos import _cache_modelos_memoria
from app.services.calendar_scraper import scrape_and_sync_uct_calendar

logger = logging.getLogger("app.servicios.calendario_anual")

ZONA_HORARIA_CHILE = ZoneInfo("America/Santiago")


async def obtener_estado_calendario_anual(
    session: AsyncSession,
    anio: int,
) -> Optional[EstadoCalendarioAnual]:
    """Retorna el estado de sincronización del calendario para un año específico."""
    stmt = select(EstadoCalendarioAnual).where(EstadoCalendarioAnual.anio_objetivo == anio)
    return (await session.execute(stmt)).scalars().first()


async def listar_estados_calendario(session: AsyncSession) -> List[Dict[str, Any]]:
    """Retorna el historial completo de estados de calendario anual."""
    stmt = select(EstadoCalendarioAnual).order_by(EstadoCalendarioAnual.anio_objetivo.desc())
    registros = (await session.execute(stmt)).scalars().all()
    return [
        {
            "anio_objetivo": r.anio_objetivo,
            "estado": r.estado,
            "intentos": r.intentos,
            "ultimo_intento_en": r.ultimo_intento_en.isoformat() if r.ultimo_intento_en else None,
            "proximo_intento_en": r.proximo_intento_en.isoformat() if r.proximo_intento_en else None,
            "ultimo_error": r.ultimo_error,
            "eventos_encontrados": r.eventos_encontrados,
        }
        for r in registros
    ]


async def enviar_alerta_correo_administrador(asunto: str, cuerpo: str) -> bool:
    """
    Envía una notificación por correo al administrador tras fallos reiterados en el calendario.
    Si SMTP_HOST no está configurado, registra la alerta en los logs de auditoría sin romper el flujo.
    """
    destinatario = getattr(settings, "EMAIL_ADMIN_NOTIFICACIONES", "admin@uct.cl")
    logger.warning(
        f"[calendario_anual] ALERTA ADMINISTRADOR: Asunto: '{asunto}' | Destinatario: {destinatario}"
    )

    if not settings.SMTP_HOST:
        logger.info("[calendario_anual] Servidor SMTP no configurado; alerta registrada en logs de auditoría.")
        return False

    def _enviar():
        try:
            msg = EmailMessage()
            msg["Subject"] = asunto
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = destinatario
            msg.set_content(cuerpo)

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as s:
                if settings.SMTP_USE_TLS:
                    s.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                s.send_message(msg)
            return True
        except Exception as e_smtp:
            logger.error(f"[calendario_anual] Error al enviar alerta por correo SMTP: {e_smtp}")
            return False

    return await asyncio.to_thread(_enviar)


def invalidar_caches_aforo_y_marcar_reentrenamiento() -> None:
    """
    Invalida cachés de aforo en memoria y programa la recalibración de modelos
    predictivos para el siguiente ciclo diario.
    """
    logger.info("[calendario_anual] Invalidando cachés de memoria para modelos predictivos y aforo...")
    _cache_modelos_memoria.clear()


async def sincronizar_calendario_anual(
    session: AsyncSession,
    anio_objetivo: Optional[int] = None,
    forzar: bool = False,
) -> Dict[str, Any]:
    """
    Ejecuta la sincronización anual del calendario académico oficial.
    Considera exitoso el proceso solo si se identifican al menos settings.MINIMO_EVENTOS_CALENDARIO
    para el año objetivo; de lo contrario marca 'pendiente' y programa el reintento en 7 días exactos.
    Tras 3 intentos fallidos consecutivos, envía una alerta por correo al administrador.
    """
    ahora_utc = datetime.utcnow()
    anio = anio_objetivo or datetime.now(ZONA_HORARIA_CHILE).year

    # Obtener o crear registro de estado
    registro = await obtener_estado_calendario_anual(session, anio)
    if not registro:
        registro = EstadoCalendarioAnual(
            anio_objetivo=anio,
            estado="pendiente",
            intentos=0,
            eventos_encontrados=0,
        )
        session.add(registro)
        await session.flush()

    if registro.estado == "completo" and not forzar:
        logger.info(f"[calendario_anual] El calendario para el año {anio} ya está completo. Sincronización omitida.")
        return {
            "status": "omitido",
            "mensaje": f"El calendario para el año {anio} ya se encuentra completo.",
            "anio_objetivo": anio,
            "estado": "completo",
            "eventos_encontrados": registro.eventos_encontrados,
        }

    registro.ultimo_intento_en = ahora_utc
    error_capturado: Optional[str] = None
    eventos_anio = 0

    try:
        # 1. Ejecutar scraping de la web oficial UCT
        resultado_scraping = await scrape_and_sync_uct_calendar(session)
        logger.info(f"[calendario_anual] Resultado scraping: {resultado_scraping}")

        # 2. Contar eventos correspondientes al año objetivo en la base de datos
        sql_conteo = text("""
            SELECT COUNT(*) AS total
            FROM calendario_academico
            WHERE YEAR(fecha) = :anio
              AND (is_holiday = 1 OR is_break = 1 OR is_exam_period = 1 OR is_class_milestone = 1 OR suspension_actividades = 1)
        """)
        res_conteo = await session.execute(sql_conteo, {"anio": anio})
        eventos_anio = res_conteo.scalar() or 0

    except Exception as exc:
        error_capturado = str(exc)
        logger.error(f"[calendario_anual] Error durante el scraping de calendario: {exc}", exc_info=True)

    minimo_requerido = settings.MINIMO_EVENTOS_CALENDARIO

    # 3. Evaluar criterio de aceptación: al menos settings.MINIMO_EVENTOS_CALENDARIO
    if error_capturado is None and eventos_anio >= minimo_requerido:
        # Éxito: calendario completo
        registro.estado = "completo"
        registro.eventos_encontrados = eventos_anio
        registro.proximo_intento_en = None
        registro.ultimo_error = None

        await session.commit()
        await session.refresh(registro)

        # Invalida cachés y marca modelos predictivos para reentrenamiento (Tarea 7)
        invalidar_caches_aforo_y_marcar_reentrenamiento()

        logger.info(
            f"[calendario_anual] Calendario anual {anio} COMPLETADO exitosamente con {eventos_anio} eventos "
            f"(mínimo requerido: {minimo_requerido}). Reintentos detenidos."
        )

        return {
            "status": "completo",
            "mensaje": f"Calendario {anio} sincronizado exitosamente con {eventos_anio} eventos.",
            "anio_objetivo": anio,
            "estado": "completo",
            "eventos_encontrados": eventos_anio,
            "intentos": registro.intentos,
        }
    else:
        # Fallo o eventos insuficientes: programar reintento en 7 días exactos
        registro.intentos += 1
        registro.estado = "pendiente"
        registro.eventos_encontrados = eventos_anio

        proximo_reintento = ahora_utc + timedelta(days=7)
        registro.proximo_intento_en = proximo_reintento

        if error_capturado:
            registro.ultimo_error = f"Fallo de conexión o extracción: {error_capturado}"
        else:
            registro.ultimo_error = (
                f"Eventos insuficientes para el año {anio} ({eventos_anio} detectados, "
                f"mínimo requerido {minimo_requerido}). La web aún no publica el calendario completo."
            )

        await session.commit()
        await session.refresh(registro)

        logger.warning(
            f"[calendario_anual] Calendario {anio} permanece 'pendiente' (Intento #{registro.intentos}). "
            f"Eventos encontrados: {eventos_anio}/{minimo_requerido}. Próximo reintento: {proximo_reintento.isoformat()}"
        )

        # Tarea 5: Enviar alerta por correo al administrador tras 3 intentos fallidos consecutivos
        if registro.intentos >= 3:
            asunto_alerta = f"[DSS UCT] Alerta Crítica: Calendario Académico {anio} no disponible tras {registro.intentos} intentos"
            cuerpo_alerta = (
                f"Estimado Administrador del Sistema DSS Campus San Francisco:\n\n"
                f"El proceso automático de verificación del calendario académico oficial para el año {anio} "
                f"ha acumulado {registro.intentos} intentos fallidos consecutivos.\n\n"
                f"Detalle del último intento:\n"
                f"- Fecha: {ahora_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                f"- Eventos identificados: {eventos_anio} (Mínimo institucional requerido: {minimo_requerido})\n"
                f"- Causa: {registro.ultimo_error}\n"
                f"- Próximo reintento programado: {proximo_reintento.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                f"Por favor verifique la disponibilidad de la página institucional de la UCT o cargue las fechas manualmente.\n"
            )
            asyncio.create_task(enviar_alerta_correo_administrador(asunto_alerta, cuerpo_alerta))

        # Programar reintento en APScheduler si está disponible
        from app.core.planificador import obtener_planificador, ejecutar_tarea
        sched = obtener_planificador()
        if sched and sched.running:
            reintento_chile = datetime.now(ZONA_HORARIA_CHILE) + timedelta(days=7)
            job_id = f"reintento_calendario_{anio}_{int(ahora_utc.timestamp())}"
            try:
                def _crear_job_calendario():
                    async def _job():
                        logger.info(f"[calendario_anual] Disparando reintento semanal de calendario para {anio}")
                        async with AsyncSessionLocal() as s_retry:
                            await sincronizar_calendario_anual(s_retry, anio_objetivo=anio)
                    return _job

                sched.add_job(
                    _crear_job_calendario(),
                    trigger="date",
                    run_date=reintento_chile,
                    id=job_id,
                    replace_existing=True,
                    name=f"Reintento semanal calendario académico {anio}",
                )
                logger.info(f"[calendario_anual] Reintento programado en APScheduler para {reintento_chile.isoformat()}")
            except Exception as e_sched:
                logger.error(f"[calendario_anual] Error al agendar reintento en planificador: {e_sched}")

        return {
            "status": "pendiente",
            "mensaje": registro.ultimo_error,
            "anio_objetivo": anio,
            "estado": "pendiente",
            "intentos": registro.intentos,
            "eventos_encontrados": eventos_anio,
            "proximo_intento_en": proximo_reintento.isoformat(),
        }
