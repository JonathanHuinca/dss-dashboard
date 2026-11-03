import asyncio
import json
import logging
try:
    import resource
except ImportError:
    resource = None
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.domain.ejecucion_tarea_models import EjecucionTarea

logger = logging.getLogger("app.planificador")

ZONA_HORARIA_CHILE = ZoneInfo("America/Santiago")


def _ahora_chile_naive() -> datetime:
    """Retorna la fecha y hora local de Chile (America/Santiago) sin tzinfo para persistencia uniforme en BD."""
    return datetime.now(ZONA_HORARIA_CHILE).replace(tzinfo=None)

# Instancia singleton de AsyncIOScheduler
planificador: Optional[AsyncIOScheduler] = None
_bloqueos_memoria: Dict[str, asyncio.Lock] = {}
_tareas_en_ejecucion_tasks: Dict[uuid.UUID, asyncio.Task] = {}


class ReentranciaError(Exception):
    """Excepción cuando una tarea ya se encuentra en ejecución con latido activo."""
    pass


class TareaNoEncontradaError(Exception):
    """Excepción cuando la tarea solicitada no existe en el catálogo."""
    pass


def _obtener_bloqueo_memoria(nombre_tarea: str) -> asyncio.Lock:
    if nombre_tarea not in _bloqueos_memoria:
        _bloqueos_memoria[nombre_tarea] = asyncio.Lock()
    return _bloqueos_memoria[nombre_tarea]


def _obtener_hora_entrenamiento_ml() -> Tuple[int, int]:
    try:
        partes = settings.HORA_ENTRENAMIENTO_DIARIO.split(":")
        return int(partes[0]), int(partes[1])
    except Exception:
        return 6, 0

_hora_ml, _minuto_ml = _obtener_hora_entrenamiento_ml()


# ---------------------------------------------------------------------------
# Handlers de tareas del sistema
# ---------------------------------------------------------------------------

async def _handler_reentrenar_modelos_ml(disparador: str = "manual") -> Dict[str, Any]:
    """
    Ejecuta el reentrenamiento mediante subproceso ('python -m app.cli entrenar-modelos')
    con prioridad baja y límite de tiempo.
    En ejecuciones automáticas matutinas (disparador != 'manual') incluye '--solo-operativos-hoy'
    para verificar primero si ese día se trabaja en cada módulo según horario y calendario académico.
    """
    import os
    import sys

    cmd = [sys.executable, "-m", "app.cli", "entrenar-modelos"]
    if disparador != "manual":
        cmd.append("--solo-operativos-hoy")
    tiempo_max_seg = max(60, settings.TIEMPO_MAXIMO_TAREA_MINUTOS * 60)

    preexec_fn = None
    if os.name != "nt":
        def _establecer_prioridad_baja():
            try:
                os.nice(10)
            except Exception:
                pass
        preexec_fn = _establecer_prioridad_baja

    logger.info(f"[planificador] Iniciando subproceso de reentrenamiento: {' '.join(cmd)}")
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=preexec_fn,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=tiempo_max_seg)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise TimeoutError(
            f"El subproceso de reentrenamiento excedió el tiempo límite de {settings.TIEMPO_MAXIMO_TAREA_MINUTOS} minutos."
        )

    stdout_str = stdout_bytes.decode("utf-8", errors="replace")
    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    if proc.returncode != 0:
        logger.error(f"[planificador] Subproceso de reentrenamiento finalizó con código {proc.returncode}:\n{stderr_str}")
        raise RuntimeError(
            f"Fallo en subproceso de entrenamiento (código {proc.returncode}): {stderr_str.strip() or stdout_str.strip()}"
        )

    # Intentar parsear el resultado estructurado JSON emitido por train.py
    resultado_detalle = None
    for linea in stdout_str.strip().split("\n"):
        if linea.startswith("__RESULTADO_JSON__:"):
            try:
                resultado_detalle = json.loads(linea.replace("__RESULTADO_JSON__:", "").strip())
                break
            except Exception:
                pass

    return {
        "resultado": "entrenamiento_completado",
        "salida_resumen": stdout_str[-800:] if len(stdout_str) > 800 else stdout_str,
        "modelos": resultado_detalle,
    }


async def _handler_purgar_conversaciones_chat() -> Dict[str, Any]:
    from app.services.servicio_chat_persistente import purgar_conversaciones_eliminadas
    async with AsyncSessionLocal() as session:
        eliminadas = await purgar_conversaciones_eliminadas(session)
        return {"resultado": "purga_completada", "conversaciones_purgadas": eliminadas}


async def _handler_sincronizar_calendario_academico() -> Dict[str, Any]:
    from app.services.calendar_scraper import scrape_and_sync_uct_calendar
    async with AsyncSessionLocal() as session:
        res = await scrape_and_sync_uct_calendar(session)
        return {"resultado": "calendario_sincronizado", "detalle": res}


async def _handler_sincronizar_smart_campus_en_vivo() -> Dict[str, Any]:
    """Ingesta horaria en tiempo real desde la API Smart Campus UCT para actualización de aforo vivo."""
    from app.services.servicio_smart_campus import sincronizar_aforo_vivo_horario
    async with AsyncSessionLocal() as session:
        res = await sincronizar_aforo_vivo_horario(session)
        if res.get("errores") and res["torniquetes"]["leidos"] == 0 and res["estacionamientos"]["leidos"] == 0:
            raise RuntimeError("; ".join(res["errores"]))
        return res


async def _handler_consolidar_smart_campus_nocturno() -> Dict[str, Any]:
    """Consolidación nocturna diaria a las 00:05 para cerrar el día anterior (D-1) con permanencias reales."""
    from app.services.servicio_smart_campus import consolidar_dia_cerrado
    async with AsyncSessionLocal() as session:
        res = await consolidar_dia_cerrado(session)
        if res.get("errores") and not res.get("rollup_asistencia") and not res.get("rollup_vehicular"):
            raise RuntimeError("; ".join(res["errores"]))
        return res


async def _handler_verificar_calendario_anual() -> Dict[str, Any]:
    from app.services.servicio_calendario_anual import sincronizar_calendario_anual
    async with AsyncSessionLocal() as session:
        return await sincronizar_calendario_anual(session)


async def _handler_tarea_prueba() -> Dict[str, Any]:
    await asyncio.sleep(2)
    return {"mensaje": "Tarea de prueba ejecutada con éxito"}


# Catálogo oficial de tareas administradas
CATALOGO_TAREAS: Dict[str, Dict[str, Any]] = {
    "reentrenar_modelos_ml": {
        "descripcion": "Reentrenamiento diario de modelos Prophet, GBR y KMeans (Campeón vs. Retador)",
        "cron_trigger": CronTrigger(hour=_hora_ml, minute=_minuto_ml, timezone=ZONA_HORARIA_CHILE),
        "cron_str": f"{_minuto_ml} {_hora_ml} * * * ({_hora_ml:02d}:{_minuto_ml:02d} AM en días hábiles operativos)",
        "handler": _handler_reentrenar_modelos_ml,
        "catchup_hora": _hora_ml,
        "catchup_minuto": _minuto_ml,
        "frecuencia": "diaria",
    },
    "purgar_conversaciones_chat": {
        "descripcion": "Purga de conversaciones eliminadas que superan período de retención legal",
        "cron_trigger": CronTrigger(hour=3, minute=0, timezone=ZONA_HORARIA_CHILE),
        "cron_str": "0 3 * * * (03:00 AM en días hábiles operativos)",
        "handler": _handler_purgar_conversaciones_chat,
        "catchup_hora": 3,
        "catchup_minuto": 0,
        "frecuencia": "diaria",
    },
    "verificar_calendario_anual": {
        "descripcion": "Verificación y sincronización anual del calendario académico oficial UCT",
        "cron_trigger": CronTrigger(month=1, day=1, hour=3, minute=0, timezone=ZONA_HORARIA_CHILE),
        "cron_str": "0 3 1 1 * (01 de enero a las 03:00 AM anual)",
        "handler": _handler_verificar_calendario_anual,
        "catchup_hora": 3,
        "catchup_minuto": 0,
        "catchup_mes": 1,
        "catchup_dia": 1,
        "frecuencia": "anual",
    },
    "sincronizar_calendario_academico": {
        "descripcion": "Sincronización mensual y verificación de calendario académico UCT mediante scraping",
        "cron_trigger": CronTrigger(day=1, hour=4, minute=0, timezone=ZONA_HORARIA_CHILE),
        "cron_str": "0 4 1 * * (Día 1 de cada mes a las 04:00 AM)",
        "handler": _handler_sincronizar_calendario_academico,
        "catchup_hora": 4,
        "catchup_minuto": 0,
        "frecuencia": "mensual",
    },
    "sincronizar_smart_campus_en_vivo": {
        "descripcion": "Ingesta horaria en vivo desde API Smart Campus UCT para aforo en tiempo real",
        "cron_trigger": CronTrigger(minute=5, timezone=ZONA_HORARIA_CHILE),
        "cron_str": "5 * * * * (Cada hora al min 5 en días y horario hábil)",
        "handler": _handler_sincronizar_smart_campus_en_vivo,
        "catchup_hora": None,
        "catchup_minuto": None,
        "frecuencia": "horaria",
    },
    "consolidar_smart_campus_nocturno": {
        "descripcion": "Consolidación nocturna diaria a las 00:05 para cerrar el día anterior (D-1)",
        "cron_trigger": CronTrigger(hour=0, minute=5, timezone=ZONA_HORARIA_CHILE),
        "cron_str": "5 0 * * * (00:05 AM tras cada jornada hábil D-1)",
        "handler": _handler_consolidar_smart_campus_nocturno,
        "catchup_hora": 0,
        "catchup_minuto": 5,
        "frecuencia": "diaria",
    },

    "tarea_prueba": {
        "descripcion": "Tarea de verificación operativa del planificador interno",
        "cron_trigger": None,
        "cron_str": "Bajo demanda (manual)",
        "handler": _handler_tarea_prueba,
        "catchup_hora": None,
        "catchup_minuto": None,
        "frecuencia": "manual",
    },
}


async def es_momento_operativo_para_tarea(
    session: AsyncSession,
    nombre_tarea: str,
    dt_eval: Optional[datetime] = None,
) -> Tuple[bool, str]:
    """
    Evalúa si una tarea automática debe ejecutarse en `dt_eval` según el horario de atención
    de los módulos, feriados legales/académicos y días no laborales (domingos).
    """
    from app.ml.orquestador_entrenamiento import (
        verificar_hora_operativa_campus,
        verificar_modulo_opera_en_fecha,
    )

    ahora = dt_eval or _ahora_chile_naive()

    if nombre_tarea == "sincronizar_smart_campus_en_vivo":
        return await verificar_hora_operativa_campus(session, ahora, margen_post_cierre_horas=1)

    if nombre_tarea in ("reentrenar_modelos_ml", "purgar_conversaciones_chat"):
        op1, m1 = await verificar_modulo_opera_en_fecha(session, 1, ahora)
        op2, m2 = await verificar_modulo_opera_en_fecha(session, 2, ahora)
        if op1 or op2:
            return True, m1 if op1 else m2
        return False, f"Día no laboral ({m1})"

    if nombre_tarea == "consolidar_smart_campus_nocturno":
        ayer = ahora - timedelta(days=1)
        op1, m1 = await verificar_modulo_opera_en_fecha(session, 1, ayer)
        op2, m2 = await verificar_modulo_opera_en_fecha(session, 2, ayer)
        if op1 or op2:
            return True, f"Jornada D-1 hábil ({ayer.strftime('%Y-%m-%d')})"
        return False, f"Jornada D-1 no laboral ({m1})"

    return True, "Programación periódica general"


async def calcular_proxima_ejecucion_habil(
    session: AsyncSession,
    nombre_tarea: str,
    ahora_cl: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Calcula la próxima fecha/hora real de ejecución saltando feriados, recesos,
    domingos sin atención y horas fuera del horario operativo del campus.
    """
    info = CATALOGO_TAREAS.get(nombre_tarea)
    if not info or not info.get("cron_trigger"):
        return None

    trigger: CronTrigger = info["cron_trigger"]
    cursor = ahora_cl or datetime.now(ZONA_HORARIA_CHILE)

    if nombre_tarea == "sincronizar_smart_campus_en_vivo":
        # Buscar hasta 14 días (336 horas) la primera ventana horaria hábil
        prev = None
        for _ in range(336):
            candidato = trigger.get_next_fire_time(prev, cursor)
            if not candidato:
                return None
            cand_naive = candidato.astimezone(ZONA_HORARIA_CHILE).replace(tzinfo=None)
            es_op, _ = await es_momento_operativo_para_tarea(session, nombre_tarea, cand_naive)
            if es_op:
                return candidato
            prev = candidato
            cursor = candidato + timedelta(seconds=1)
        return trigger.get_next_fire_time(None, ahora_cl or datetime.now(ZONA_HORARIA_CHILE))

    if nombre_tarea in ("reentrenar_modelos_ml", "purgar_conversaciones_chat", "consolidar_smart_campus_nocturno"):
        # Buscar hasta 30 días el próximo día hábil operativo
        prev = None
        for _ in range(30):
            candidato = trigger.get_next_fire_time(prev, cursor)
            if not candidato:
                return None
            cand_naive = candidato.astimezone(ZONA_HORARIA_CHILE).replace(tzinfo=None)
            es_op, _ = await es_momento_operativo_para_tarea(session, nombre_tarea, cand_naive)
            if es_op:
                return candidato
            prev = candidato
            cursor = candidato + timedelta(seconds=1)
        return trigger.get_next_fire_time(None, ahora_cl or datetime.now(ZONA_HORARIA_CHILE))

    return trigger.get_next_fire_time(None, cursor)



# ---------------------------------------------------------------------------
# Gestión de Huérfanas y Latidos
# ---------------------------------------------------------------------------

async def limpiar_tareas_huerfanas(al_iniciar: bool = False) -> int:
    """Limpia tareas 'en_curso' cuyo latido superó los 15 minutos o interrumpidas por reinicio."""
    ahora_local = _ahora_chile_naive()
    limite = ahora_local - timedelta(minutes=15)
    async with AsyncSessionLocal() as session:
        condiciones = [EjecucionTarea.estado == "en_curso"]
        if not al_iniciar:
            condiciones.append(EjecucionTarea.latido_en < limite)
        stmt = (
            update(EjecucionTarea)
            .where(*condiciones)
            .values(
                estado="fallido",
                fin_en=ahora_local,
                error="Interrumpido por reinicio o latido vencido (huérfana)",
            )
        )
        res = await session.execute(stmt)
        await session.commit()
        afectadas = res.rowcount
        if afectadas > 0:
            logger.warning(f"[planificador] Se limpiaron {afectadas} tareas huérfanas en la base de datos.")
        return afectadas


async def _actualizar_latido_periodico(ejecucion_id: uuid.UUID, stop_event: asyncio.Event) -> None:
    """Actualiza el latido de la tarea cada 30 segundos mientras siga activa."""
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=30.0)
            break
        except asyncio.TimeoutError:
            try:
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(EjecucionTarea)
                        .where(
                            EjecucionTarea.id == ejecucion_id,
                            EjecucionTarea.estado == "en_curso",
                        )
                        .values(latido_en=_ahora_chile_naive())
                    )
                    await session.commit()
            except Exception as e_hb:
                logger.error(f"[planificador] Error en latido para {ejecucion_id}: {e_hb}")


# ---------------------------------------------------------------------------
# Motor de Ejecución de Tareas
# ---------------------------------------------------------------------------

async def ejecutar_tarea(
    nombre: str,
    disparador: str = "manual",
    usuario_id: Optional[int] = None,
) -> EjecucionTarea:
    """
    Ejecuta una tarea controlando reentrancia atómica en BD, latido, timeout y memoria.
    Lanza ReentranciaError si la tarea ya está en curso con latido activo.
    """
    if nombre not in CATALOGO_TAREAS:
        raise TareaNoEncontradaError(f"La tarea '{nombre}' no está registrada en el catálogo.")

    info_tarea = CATALOGO_TAREAS[nombre]
    lock = _obtener_bloqueo_memoria(nombre)

    async with lock:
        ahora = _ahora_chile_naive()
        limite_latido = ahora - timedelta(minutes=15)

        async with AsyncSessionLocal() as session:
            # 1. Comprobar reentrancia en BD: fila 'en_curso' con latido activo (< 15 min)
            stmt = select(EjecucionTarea).where(
                EjecucionTarea.tarea == nombre,
                EjecucionTarea.estado == "en_curso",
                EjecucionTarea.latido_en >= limite_latido,
            )
            activa = (await session.execute(stmt)).scalars().first()
            if activa:
                if disparador == "manual":
                    raise ReentranciaError(
                        f"La tarea '{nombre}' ya se encuentra en ejecución (latido activo: {activa.latido_en.isoformat()})."
                    )
                else:
                    # En ejecuciones automáticas/recuperación, registramos la omisión
                    omitida = EjecucionTarea(
                        tarea=nombre,
                        disparador=disparador,
                        estado="omitido",
                        inicio_en=ahora,
                        fin_en=ahora,
                        latido_en=ahora,
                        usuario_id=usuario_id,
                        resumen_json=json.dumps({"motivo": "Tarea en curso con latido activo"}, ensure_ascii=False),
                    )
                    session.add(omitida)
                    await session.commit()
                    await session.refresh(omitida)
                    logger.info(f"[planificador] Tarea '{nombre}' omitida: ya en ejecución con latido activo.")
                    return omitida

            # 2. Si existían tareas 'en_curso' con latido vencido (>= 15 min), marcarlas como fallidas
            stmt_limpiar = (
                update(EjecucionTarea)
                .where(
                    EjecucionTarea.tarea == nombre,
                    EjecucionTarea.estado == "en_curso",
                    EjecucionTarea.latido_en < limite_latido,
                )
                .values(
                    estado="fallido",
                    fin_en=ahora,
                    error="Latido vencido (más de 15 minutos sin señal de vida)",
                )
            )
            await session.execute(stmt_limpiar)

            # 3. Crear el nuevo registro de ejecución en estado 'en_curso'
            nueva_ejecucion = EjecucionTarea(
                tarea=nombre,
                disparador=disparador,
                estado="en_curso",
                inicio_en=ahora,
                latido_en=ahora,
                usuario_id=usuario_id,
            )
            session.add(nueva_ejecucion)
            await session.commit()
            await session.refresh(nueva_ejecucion)
            ejecucion_id = nueva_ejecucion.id

    # 4. Lanzar la ejecución asíncrona controlada
    async def _proceso_ejecucion():
        stop_event = asyncio.Event()
        tarea_latido = asyncio.create_task(_actualizar_latido_periodico(ejecucion_id, stop_event))
        tiempo_max_seg = max(60, settings.TIEMPO_MAXIMO_TAREA_MINUTOS * 60)
        estado_final = "exitoso"
        error_msg = None
        resumen_dict = None

        try:
            handler = info_tarea["handler"]
            if nombre == "reentrenar_modelos_ml":
                resumen_dict = await asyncio.wait_for(handler(disparador=disparador), timeout=tiempo_max_seg)
            else:
                resumen_dict = await asyncio.wait_for(handler(), timeout=tiempo_max_seg)
        except asyncio.TimeoutError:
            estado_final = "fallido"
            error_msg = f"Tiempo de ejecución cancelado por exceder límite de {settings.TIEMPO_MAXIMO_TAREA_MINUTOS} minutos."
            logger.error(f"[planificador] Tarea '{nombre}' ({ejecucion_id}) cancelada por timeout.")
        except Exception as exc:
            estado_final = "fallido"
            error_msg = str(exc)
            logger.error(f"[planificador] Error en tarea '{nombre}' ({ejecucion_id}): {exc}", exc_info=True)
        finally:
            stop_event.set()
            tarea_latido.cancel()
            _tareas_en_ejecucion_tasks.pop(ejecucion_id, None)

            # Medición de memoria pico
            memoria_mb = None
            if resource:
                try:
                    memoria_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
                except Exception:
                    pass

            resumen_json_str = json.dumps(resumen_dict, ensure_ascii=False) if resumen_dict is not None else None
            fin_tiempo = _ahora_chile_naive()

            async with AsyncSessionLocal() as session_fin:
                await session_fin.execute(
                    update(EjecucionTarea)
                    .where(EjecucionTarea.id == ejecucion_id)
                    .values(
                        estado=estado_final,
                        fin_en=fin_tiempo,
                        latido_en=fin_tiempo,
                        error=error_msg,
                        resumen_json=resumen_json_str,
                        memoria_pico_mb=memoria_mb,
                    )
                )
                await session_fin.commit()

            # Tarea 4: Reintento tras 30 minutos si falla el reentrenamiento de modelos ML
            if estado_final == "fallido" and nombre == "reentrenar_modelos_ml" and disparador != "reintento":
                if planificador and planificador.running:
                    reintento_dt = datetime.now(ZONA_HORARIA_CHILE) + timedelta(minutes=30)
                    job_id = f"reintento_ml_{int(datetime.now(ZONA_HORARIA_CHILE).timestamp())}"
                    logger.warning(
                        f"[planificador] Tarea '{nombre}' ({ejecucion_id}) falló. "
                        f"Programando reintento tras 30 minutos para {reintento_dt.strftime('%Y-%m-%d %H:%M:%S')} (Job ID: {job_id})"
                    )
                    def _crear_job_reintento(n=nombre):
                        async def _job_reintento():
                            logger.info(f"[planificador] Ejecutando reintento programado de '{n}' tras 30 minutos...")
                            await ejecutar_tarea(n, disparador="reintento")
                        return _job_reintento

                    planificador.add_job(
                        _crear_job_reintento(nombre),
                        trigger="date",
                        run_date=reintento_dt,
                        id=job_id,
                        name=f"Reintento tras 30m de {nombre}",
                    )

    tarea_coro = asyncio.create_task(_proceso_ejecucion())
    _tareas_en_ejecucion_tasks[ejecucion_id] = tarea_coro
    return nueva_ejecucion



# ---------------------------------------------------------------------------
# Mecanismo de Catch-up (Recuperación al inicio)
# ---------------------------------------------------------------------------

async def ejecutar_recuperacion_al_inicio() -> None:
    """
    Verifica si las tareas programadas periódicas no se ejecutaron debido al apagado
    del contenedor. Si el momento programado ya pasó, el día/hora actual es laboralmente
    hábil y no hay registro exitoso hoy, se despacha con disparador='recuperacion'.
    """
    ahora_chile = _ahora_chile_naive()
    logger.info(f"[planificador] Evaluando catch-up de tareas al inicio (Hora local: {ahora_chile.strftime('%Y-%m-%d %H:%M:%S')})...")

    async with AsyncSessionLocal() as session:
        for nombre, info in CATALOGO_TAREAS.items():
            frecuencia = info.get("frecuencia")
            if frecuencia == "horaria":
                es_op, motivo_op = await es_momento_operativo_para_tarea(session, nombre, ahora_chile)
                if not es_op:
                    logger.info(f"[planificador] Catch-up horario omitido para '{nombre}': {motivo_op}")
                    continue
                hace_una_hora = ahora_chile - timedelta(minutes=55)
                stmt_h = select(EjecucionTarea).where(
                    EjecucionTarea.tarea == nombre,
                    EjecucionTarea.inicio_en >= hace_una_hora,
                    EjecucionTarea.estado.in_(["exitoso", "en_curso"]),
                )
                ejecutada_h = (await session.execute(stmt_h)).scalars().first()
                if not ejecutada_h:
                    logger.info(f"[planificador] Ejecutando sincronización horaria inicial para '{nombre}'...")
                    try:
                        await ejecutar_tarea(nombre, disparador="recuperacion")
                    except Exception as exc_h:
                        logger.error(f"[planificador] Error en catch-up horario de '{nombre}': {exc_h}")
                continue

            if frecuencia not in ("diaria", "anual") or info.get("catchup_hora") is None:
                continue

            es_op, motivo_op = await es_momento_operativo_para_tarea(session, nombre, ahora_chile)
            if not es_op:
                logger.info(f"[planificador] Catch-up diario omitido para '{nombre}': {motivo_op}")
                continue

            hora_prog = info["catchup_hora"]
            minuto_prog = info["catchup_minuto"]

            if frecuencia == "diaria":
                prevista = ahora_chile.replace(hour=hora_prog, minute=minuto_prog, second=0, microsecond=0)
                limite_tiempo = prevista - timedelta(minutes=5)
            elif frecuencia == "anual":
                mes_prog = info.get("catchup_mes", 1)
                dia_prog = info.get("catchup_dia", 1)
                prevista = ahora_chile.replace(month=mes_prog, day=dia_prog, hour=hora_prog, minute=minuto_prog, second=0, microsecond=0)
                limite_tiempo = datetime(ahora_chile.year, 1, 1, 0, 0, 0)
            else:
                continue

            if ahora_chile >= prevista:
                stmt = select(EjecucionTarea).where(
                    EjecucionTarea.tarea == nombre,
                    EjecucionTarea.inicio_en >= limite_tiempo,
                    EjecucionTarea.estado.in_(["exitoso", "en_curso"]),
                )
                ejecutada = (await session.execute(stmt)).scalars().first()

                if not ejecutada:
                    logger.warning(
                        f"[planificador] Tarea '{nombre}' debía ejecutarse el {prevista.strftime('%Y-%m-%d %H:%M')} "
                        "y no ocurrió por apagado del contenedor. Ejecutando catch-up ('recuperacion')..."
                    )
                    try:
                        await ejecutar_tarea(nombre, disparador="recuperacion")
                    except Exception as exc:
                        logger.error(f"[planificador] Error en catch-up de '{nombre}': {exc}")



# ---------------------------------------------------------------------------
# Ciclo de Vida del Planificador
# ---------------------------------------------------------------------------

_tarea_monitor_reloj: Optional[asyncio.Task] = None


async def _monitor_reloj_planificador() -> None:
    """
    Despierta periódicamente el planificador y verifica que las tareas horarias no se pierdan
    en horario hábil ante derivas entre CLOCK_MONOTONIC y CLOCK_REALTIME en contenedores Docker.
    """
    while planificador and planificador.running:
        try:
            await asyncio.sleep(20)
            if not planificador or not planificador.running:
                break
            planificador.wakeup()

            ahora_chile = _ahora_chile_naive()
            if ahora_chile.minute >= 5:
                inicio_ventana_hora = ahora_chile.replace(minute=0, second=0, microsecond=0)
                async with AsyncSessionLocal() as session:
                    es_op, _ = await es_momento_operativo_para_tarea(
                        session, "sincronizar_smart_campus_en_vivo", ahora_chile
                    )
                    if not es_op:
                        continue
                    stmt_h = select(EjecucionTarea).where(
                        EjecucionTarea.tarea == "sincronizar_smart_campus_en_vivo",
                        EjecucionTarea.inicio_en >= inicio_ventana_hora,
                        EjecucionTarea.estado.in_(["exitoso", "en_curso"]),
                    )
                    ejecutada_esta_hora = (await session.execute(stmt_h)).scalars().first()
                    if not ejecutada_esta_hora:
                        logger.info(
                            f"[planificador] Detectada ventana horaria hábil sin ejecución desde {inicio_ventana_hora.strftime('%H:%M')}. "
                            "Disparando 'sincronizar_smart_campus_en_vivo'..."
                        )
                        await ejecutar_tarea("sincronizar_smart_campus_en_vivo", disparador="programado")
        except asyncio.CancelledError:
            break
        except Exception as exc_mon:
            logger.debug(f"[planificador] Monitor de reloj: {exc_mon}")


async def iniciar_planificador() -> None:
    """Inicializa APScheduler, limpia huérfanas y evalúa catch-up si PLANIFICADOR_ACTIVO es true."""
    global planificador, _tarea_monitor_reloj
    if not settings.PLANIFICADOR_ACTIVO:
        logger.info("[planificador] PLANIFICADOR_ACTIVO es falso. Planificador no iniciado.")
        return

    logger.info("[planificador] Iniciando APScheduler interno en contenedor API...")
    
    # 1. Limpieza inicial de huérfanas interrumpidas por reinicio
    await limpiar_tareas_huerfanas(al_iniciar=True)

    # 2. Instanciación del scheduler con tolerancia ilimitada a desfases de reloj (misfire_grace_time=None)
    planificador = AsyncIOScheduler(
        timezone=ZONA_HORARIA_CHILE,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": None,
        },
    )

    for nombre, info in CATALOGO_TAREAS.items():
        trigger = info.get("cron_trigger")
        if trigger:
            # Función envoltorio para disparar con disparador='programado' solo en días/horas operativas
            def _crear_job(n=nombre):
                async def _job():
                    async with AsyncSessionLocal() as session_op:
                        es_op, motivo_op = await es_momento_operativo_para_tarea(session_op, n)
                        if not es_op:
                            logger.info(f"[planificador] Ejecución programada de '{n}' pospuesta: {motivo_op}")
                            return
                    logger.info(f"[planificador] Disparando tarea programada: {n}")
                    await ejecutar_tarea(n, disparador="programado")
                return _job

            planificador.add_job(
                _crear_job(nombre),
                trigger=trigger,
                id=nombre,
                replace_existing=True,
                name=info["descripcion"],
                misfire_grace_time=None,
                coalesce=True,
            )
            logger.info(f"[planificador] Registrada tarea cron '{nombre}': {info['cron_str']}")

    planificador.start()
    logger.info("[planificador] APScheduler activo y en ejecución.")

    # 3. Catch-up al inicio y monitor continuo de reloj
    asyncio.create_task(ejecutar_recuperacion_al_inicio())
    _tarea_monitor_reloj = asyncio.create_task(_monitor_reloj_planificador())


async def detener_planificador() -> None:
    """Detiene APScheduler limpiamente durante el apagado del servidor."""
    global planificador, _tarea_monitor_reloj
    if _tarea_monitor_reloj and not _tarea_monitor_reloj.done():
        _tarea_monitor_reloj.cancel()
        _tarea_monitor_reloj = None
    if planificador and planificador.running:
        logger.info("[planificador] Deteniendo APScheduler...")
        planificador.shutdown(wait=False)
        planificador = None
        logger.info("[planificador] APScheduler detenido.")


def es_planificador_activo() -> bool:
    """Retorna True si el planificador APScheduler está instanciado y en ejecución."""
    global planificador
    return bool(planificador and planificador.running)


def obtener_planificador() -> Optional[AsyncIOScheduler]:
    """Retorna la instancia global activa del planificador."""
    global planificador
    return planificador
