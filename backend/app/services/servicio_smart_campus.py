"""
servicio_smart_campus.py — Servicio de Sincronización y Procesamiento API Smart Campus UCT.

Implementa la arquitectura de Doble Pipeline:
1. Ingesta Horaria en Vivo: sincroniza eventos del día en curso de forma incremental e idempotente
   para alimentar el aforo actual (KPIs en vivo) de biblioteca y los 3 sectores de estacionamiento.
2. Consolidación Diaria Nocturna: consolida a las 00:05 horas el día cerrado (D-1), emparejando
   sesiones completas, calculando permanencias reales, imputando salidas no marcadas y actualizando rollups.
"""
import asyncio
import hashlib
import json
import logging
import re
import statistics
from decimal import Decimal
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import delete, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.smart_campus_adapter import SmartCampusAdapter, SmartCampusAPIError
from app.core.config import settings
from app.core.security import (
    encrypt_vehicle_patente,
    pseudonymize_person,
    pseudonymize_vehicle,
)
from app.core.tiempo import ZONA_CHILE, ahora_chile_naive
from app.domain.models import (
    Espacio,
    EstadoSincronizacionFuente,
    EventoAsistencia,
    EventoVehicular,
    RollupHistoricoDiario,
    SectorEstacionamiento,
)
from app.services.ingestion_service import invalidar_caches_recinto_y_actualizar_predicciones

logger = logging.getLogger("app.services.smart_campus")


async def registrar_estado_sincronizacion(
    db: AsyncSession,
    fuente: str,
    espacio_id: int,
    fecha_sincronizada: date,
    filas_leidas: int,
    filas_insertadas: int,
    filas_duplicadas: int,
    estado: str,
    ultimo_error: Optional[str] = None,
) -> EstadoSincronizacionFuente:
    """
    Registra o actualiza el registro de auditoría de sincronización por fuente y espacio.
    """
    stmt = (
        select(EstadoSincronizacionFuente)
        .where(
            EstadoSincronizacionFuente.fuente == fuente,
            EstadoSincronizacionFuente.espacio_id == espacio_id,
        )
    )
    res = await db.execute(stmt)
    registro = res.scalar_one_or_none()

    from zoneinfo import ZoneInfo
    ahora = datetime.now(ZoneInfo("America/Santiago")).replace(tzinfo=None)
    if not registro:
        registro = EstadoSincronizacionFuente(
            fuente=fuente,
            espacio_id=espacio_id,
            ultima_fecha_sincronizada=fecha_sincronizada,
            ultima_ejecucion_en=ahora,
            filas_leidas=filas_leidas,
            filas_insertadas=filas_insertadas,
            filas_duplicadas=filas_duplicadas,
            estado=estado,
            ultimo_error=ultimo_error,
        )
        db.add(registro)
    else:
        registro.ultima_fecha_sincronizada = fecha_sincronizada
        registro.ultima_ejecucion_en = ahora
        registro.filas_leidas = filas_leidas
        registro.filas_insertadas = filas_insertadas
        registro.filas_duplicadas = filas_duplicadas
        registro.estado = estado
        registro.ultimo_error = ultimo_error

    await db.commit()
    await db.refresh(registro)
    return registro


# =============================================================================
# PIPELINE 1: INGESTA HORARIA EN VIVO (AFORO EN TIEMPO REAL)
# =============================================================================

def _parse_dt_chile_naive(val: Any) -> Optional[datetime]:
    """Normaliza ISO o datetime (incluyendo sufijo Z/+00:00) a hora local de Chile naive."""
    if not val:
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        try:
            dt = datetime.fromisoformat(str(val).strip().replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is not None:
        return dt.astimezone(ZONA_CHILE).replace(tzinfo=None)
    return dt


def _clasificar_sentido_smart_campus(sentido: Any, vehiculo: bool = False) -> str:
    tokens = set(re.findall(r"[a-z]+", str(sentido or "").strip().lower()))
    if vehiculo:
        if tokens & {"alejandose", "salida", "out", "egreso", "exit"}:
            return "salida"
        return "entrada"
    if tokens & {"salida", "out", "egreso", "exit"}:
        return "salida"
    if tokens & {"entrada", "in", "ingreso", "entry"}:
        return "entrada"
    return "entrada"


async def sincronizar_aforo_vivo_horario(
    db: AsyncSession,
    espacio_id_peatonal: int = 1,
    espacio_id_vehicular: int = 2,
    desde_manual: Optional[date] = None,
    hasta_manual: Optional[date] = None,
    fuente: str = "todas",
) -> Dict[str, Any]:
    """
    Sincroniza de forma incremental e idempotente los eventos desde la última fecha
    registrada en la base de datos (recuperación automática de brecha) hasta hoy.
    Verifica las claves primarias existentes para no duplicar ni alterar los datos previos.
    """
    from sqlalchemy import text

    fuente_norm = (fuente or "todas").strip().lower()
    sinc_torniquetes = fuente_norm in ("todas", "torniquetes", "biblioteca")
    sinc_estacionamientos = fuente_norm in ("todas", "estacionamientos", "vehicular")

    hoy = hasta_manual or ahora_chile_naive().date()
    limite_retroceso = hoy - timedelta(days=45)
    adaptador = SmartCampusAdapter()

    # Determinar fecha de inicio incremental para Biblioteca (torniquetes)
    if desde_manual:
        desde_peatonal = desde_manual
    elif sinc_torniquetes:
        fila_max_p = (
            await db.execute(
                text("SELECT CAST(MAX(time) AS DATE) FROM eventos_asistencia WHERE espacio_id = :espacio_id"),
                {"espacio_id": espacio_id_peatonal},
            )
        ).scalar()
        if fila_max_p and isinstance(fila_max_p, str):
            fila_max_p = date.fromisoformat(fila_max_p[:10])
        desde_peatonal = max(fila_max_p, limite_retroceso) if (fila_max_p and fila_max_p <= hoy) else hoy
    else:
        desde_peatonal = hoy

    # Determinar fecha de inicio incremental para Estacionamientos (ANPR)
    if desde_manual:
        desde_vehicular = desde_manual
    elif sinc_estacionamientos:
        fila_max_v = (
            await db.execute(
                text("SELECT CAST(MAX(time) AS DATE) FROM eventos_vehiculares WHERE espacio_id = :espacio_id"),
                {"espacio_id": espacio_id_vehicular},
            )
        ).scalar()
        if fila_max_v and isinstance(fila_max_v, str):
            fila_max_v = date.fromisoformat(fila_max_v[:10])
        desde_vehicular = max(fila_max_v, limite_retroceso) if (fila_max_v and fila_max_v <= hoy) else hoy
    else:
        desde_vehicular = hoy

    resumen = {
        "fecha": hoy.isoformat(),
        "fuente": fuente_norm,
        "rango_torniquetes": f"{desde_peatonal.isoformat()} a {hoy.isoformat()}",
        "rango_estacionamientos": f"{desde_vehicular.isoformat()} a {hoy.isoformat()}",
        "torniquetes": {"leidos": 0, "insertados": 0, "duplicados": 0},
        "estacionamientos": {"leidos": 0, "insertados": 0, "duplicados": 0},
        "errores": [],
    }

    # 1. Sincronizar Torniquetes de Biblioteca
    if sinc_torniquetes:
      try:
        raw_torniquetes = await adaptador.obtener_marcajes_torniquetes(desde=desde_peatonal, hasta=hoy)
        resumen["torniquetes"]["leidos"] = len(raw_torniquetes)

        if raw_torniquetes:
            desde_dt_p = datetime.combine(desde_peatonal, time(0, 0))
            hasta_excl_dt_p = datetime.combine(hoy + timedelta(days=1), time(0, 0))
            res_existentes = await db.execute(
                text("""
                    SELECT time, person_id_hash
                    FROM eventos_asistencia
                    WHERE espacio_id = :espacio_id
                      AND time >= :desde_dt
                      AND time < :hasta_excl_dt
                """),
                {"espacio_id": espacio_id_peatonal, "desde_dt": desde_dt_p, "hasta_excl_dt": hasta_excl_dt_p},
            )
            existentes_set = {(row[0], row[1]) for row in res_existentes.fetchall()}

            # Contabilizar marcajes por persona-día en el lote descargado
            conteo_persona_dia: Dict[tuple, int] = {}
            eventos_preparados = []
            for idx_ev, r in enumerate(raw_torniquetes):
                fecha_str = r.get("fecha", "")
                if not fecha_str:
                    continue
                dt_evento = _parse_dt_chile_naive(fecha_str)
                if not dt_evento:
                    continue
                raw_id = r.get("matricula") or r.get("id_visitante") or ""
                if raw_id:
                    person_hash = pseudonymize_person(str(raw_id).strip())
                else:
                    puerta_ev = str(r.get("puerta") or r.get("acceso") or "desc")[:12]
                    digest_ev = hashlib.sha256(f"{dt_evento.isoformat()}_{puerta_ev}_{idx_ev}".encode()).hexdigest()[:10]
                    person_hash = f"sin_id_{dt_evento.strftime('%Y%m%d%H%M%S')}_{digest_ev}"
                clave_pd = (person_hash, dt_evento.date())
                conteo_persona_dia[clave_pd] = conteo_persona_dia.get(clave_pd, 0) + 1
                eventos_preparados.append((dt_evento, person_hash, r))

            insertados = 0
            duplicados = 0
            en_lote = 0

            for dt_evento, person_hash, r in eventos_preparados:
                clave_pk = (dt_evento, person_hash)
                if clave_pk in existentes_set:
                    duplicados += 1
                    continue

                es_salida = _clasificar_sentido_smart_campus(r.get("sentido"), vehiculo=False) == "salida"
                puerta = r.get("puerta") or r.get("acceso") or "Torniquete"
                total_m = conteo_persona_dia.get((person_hash, dt_evento.date()), 1)

                nuevo_evento = EventoAsistencia(
                    time=dt_evento,
                    espacio_id=espacio_id_peatonal,
                    person_id_hash=person_hash,
                    door_entrada=None if es_salida else puerta,
                    door_salida=puerta if es_salida else None,
                    primera_entrada=None if es_salida else dt_evento,
                    ultima_salida=dt_evento if es_salida else None,
                    salida_imputada=False,
                    entrada_imputada=False,
                    permanencia_min=None,
                    marcajes_totales=min(total_m, 32000),
                    alerta_coherencia_fechas=False,
                    alerta_marcajes=bool(total_m > 4),
                    carrera=r.get("detalle_estamento") if r.get("estamento") == "Estudiante" else None,
                    facultad=r.get("estamento"),
                    estamento=r.get("estamento") or "Estudiante",
                )
                db.add(nuevo_evento)
                existentes_set.add(clave_pk)
                insertados += 1
                en_lote += 1

                if en_lote >= 500:
                    await db.commit()
                    en_lote = 0

            if en_lote > 0:
                await db.commit()

            if insertados > 0:
                # Enriquecer carrera y facultad con CROSS APPLY TOP 1 para evitar ambigüedad ante duplicados en dim_estudiante_carrera
                desde_dt_upd = datetime.combine(desde_peatonal, time(0, 0))
                await db.execute(
                    text("""
                        UPDATE ea
                        SET ea.carrera = dec.carr_nombre,
                            ea.facultad = CASE
                                WHEN dec.facultad IS NOT NULL AND dec.facultad <> 'Facultad UCT' THEN dec.facultad
                                ELSE COALESCE(ea.facultad, dec.facultad)
                            END
                        FROM eventos_asistencia ea
                        CROSS APPLY (
                            SELECT TOP 1 carr_nombre, facultad
                            FROM dim_estudiante_carrera d
                            WHERE d.person_id_hash = ea.person_id_hash
                            ORDER BY d.id DESC
                        ) dec
                        WHERE ea.espacio_id = :espacio_id
                          AND ea.time >= :desde_dt
                    """),
                    {"espacio_id": espacio_id_peatonal, "desde_dt": desde_dt_upd},
                )
                await db.commit()

            resumen["torniquetes"]["insertados"] = insertados
            resumen["torniquetes"]["duplicados"] = duplicados

        await registrar_estado_sincronizacion(
            db,
            fuente="torniquetes",
            espacio_id=espacio_id_peatonal,
            fecha_sincronizada=hoy,
            filas_leidas=resumen["torniquetes"]["leidos"],
            filas_insertadas=resumen["torniquetes"]["insertados"],
            filas_duplicadas=resumen["torniquetes"]["duplicados"],
            estado="exitoso",
        )
      except Exception as exc:
          try:
              await db.rollback()
          except Exception:
              pass
          logger.error(f"[SmartCampus] Error en sincronización horaria de torniquetes: {exc}")
          resumen["errores"].append(f"Torniquetes: {str(exc)}")
          await registrar_estado_sincronizacion(
              db,
              fuente="torniquetes",
              espacio_id=espacio_id_peatonal,
              fecha_sincronizada=hoy,
              filas_leidas=resumen["torniquetes"]["leidos"],
              filas_insertadas=resumen["torniquetes"]["insertados"],
              filas_duplicadas=resumen["torniquetes"]["duplicados"],
              estado="fallido",
              ultimo_error=str(exc),
          )

    # 2. Sincronizar Pasos de Estacionamientos (los 3 sectores)
    if sinc_estacionamientos:
      try:
        raw_estacionamientos = await adaptador.obtener_pasos_estacionamientos(
            desde=desde_vehicular,
            hasta=hoy,
            solo_completas=True,
        )
        resumen["estacionamientos"]["leidos"] = len(raw_estacionamientos)

        if raw_estacionamientos:
            desde_dt_v = datetime.combine(desde_vehicular, time(0, 0))
            hasta_excl_dt_v = datetime.combine(hoy + timedelta(days=1), time(0, 0))
            res_v = await db.execute(
                text("""
                    SELECT time, patente_hash, camara
                    FROM eventos_vehiculares
                    WHERE espacio_id = :espacio_id
                      AND time >= :desde_dt
                      AND time < :hasta_excl_dt
                """),
                {"espacio_id": espacio_id_vehicular, "desde_dt": desde_dt_v, "hasta_excl_dt": hasta_excl_dt_v},
            )
            v_existentes_set = {(row[0], row[1], row[2]) for row in res_v.fetchall()}

            v_insertados = 0
            v_duplicados = 0
            v_en_lote = 0

            for r in raw_estacionamientos:
                fecha_str = r.get("fecha", "")
                if not fecha_str:
                    continue
                dt_evento = _parse_dt_chile_naive(fecha_str)
                if not dt_evento:
                    continue

                patente_raw = str(r.get("patente", "")).strip().upper()
                if not patente_raw:
                    continue

                try:
                    patente_hash, patente_cifrada = encrypt_vehicle_patente(patente_raw)
                except Exception:
                    patente_hash = pseudonymize_vehicle(patente_raw)
                    patente_cifrada = f"CIPHER_{patente_hash[:16]}"

                camara = r.get("camara") or r.get("acceso") or "ANPR"
                clave_v = (dt_evento, patente_hash, camara)
                if clave_v in v_existentes_set:
                    v_duplicados += 1
                    continue

                direccion = _clasificar_sentido_smart_campus(r.get("sentido"), vehiculo=True)

                nuevo_vehicular = EventoVehicular(
                    time=dt_evento,
                    espacio_id=espacio_id_vehicular,
                    patente_hash=patente_hash,
                    patente_cifrada=patente_cifrada,
                    camara=camara,
                    direccion=direccion,
                    tipo_vehiculo=r.get("tipo_vehiculo"),
                    marca=r.get("marca"),
                    color=r.get("color"),
                    calidad_lectura="ok",
                )
                db.add(nuevo_vehicular)
                v_existentes_set.add(clave_v)
                v_insertados += 1
                v_en_lote += 1

                if v_en_lote >= 500:
                    await db.commit()
                    v_en_lote = 0

            if v_en_lote > 0:
                await db.commit()

            resumen["estacionamientos"]["insertados"] = v_insertados
            resumen["estacionamientos"]["duplicados"] = v_duplicados

        await registrar_estado_sincronizacion(
            db,
            fuente="estacionamientos",
            espacio_id=espacio_id_vehicular,
            fecha_sincronizada=hoy,
            filas_leidas=resumen["estacionamientos"]["leidos"],
            filas_insertadas=resumen["estacionamientos"]["insertados"],
            filas_duplicadas=resumen["estacionamientos"]["duplicados"],
            estado="exitoso",
        )
      except Exception as exc:
          try:
              await db.rollback()
          except Exception:
              pass
          logger.error(f"[SmartCampus] Error en sincronización horaria de estacionamientos: {exc}")
          resumen["errores"].append(f"Estacionamientos: {str(exc)}")
          await registrar_estado_sincronizacion(
              db,
              fuente="estacionamientos",
              espacio_id=espacio_id_vehicular,
              fecha_sincronizada=hoy,
              filas_leidas=resumen["estacionamientos"]["leidos"],
              filas_insertadas=resumen["estacionamientos"]["insertados"],
              filas_duplicadas=resumen["estacionamientos"]["duplicados"],
              estado="fallido",
              ultimo_error=str(exc),
          )

    # Invalidar cachés del recinto sincronizado
    if sinc_torniquetes:
        await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id_peatonal)
    if sinc_estacionamientos:
        await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id_vehicular)

    return resumen


# =============================================================================
# PIPELINE 2: CONSOLIDACIÓN DIARIA NOCTURNA (D-1 DÍA CERRADO)
# =============================================================================

async def consolidar_dia_cerrado(
    db: AsyncSession,
    fecha_objetivo: Optional[date] = None,
    espacio_id_peatonal: int = 1,
    espacio_id_vehicular: int = 2,
    fuente: str = "todas",
) -> Dict[str, Any]:
    """
    Consolida un día completo cerrado (por defecto ayer D-1).
    Al contar con el 100% de entradas y salidas ocurridas:
    1. Detecta dinámicamente si el día operó bajo régimen regular o campaña 24 Horas / turno extendido.
    2. Determina la hora oficial de cierre según horarios_operacion (evitando horas fijas cableadas).
    3. Si hubo régimen nocturno (cierre_dia_siguiente o 24h), extiende la ventana de búsqueda de salidas
       hacia la madrugada siguiente (hasta 07:15 AM) para emparejar sesiones transnochadas (cross-midnight).
    4. Imputa salidas a estudiantes que no registraron egreso usando la hora de cierre contextual
       (diurna habitual o fin de turno nocturno en 24h).
    5. Dispone de fallback directo a la base de datos local (eventos_asistencia y eventos_vehiculares)
       si la API externa Smart Campus no responde o se opera sin conexión institucional.
    6. Calcula totales, personas/vehículos únicos y mediana de permanencia para el rollup histórico diario.
    """
    from app.services.config_service import get_horarios_operacion

    fuente_norm = (fuente or "todas").strip().lower()
    cons_torniquetes = fuente_norm in ("todas", "torniquetes", "biblioteca")
    cons_estacionamientos = fuente_norm in ("todas", "estacionamientos", "vehicular")

    ayer_raw = fecha_objetivo or (ahora_chile_naive().date() - timedelta(days=1))
    ayer: date = ayer_raw.date() if isinstance(ayer_raw, datetime) else ayer_raw
    dia_siguiente = ayer + timedelta(days=1)
    adaptador = SmartCampusAdapter()

    resumen = {
        "fecha_consolidada": ayer.isoformat(),
        "fuente": fuente_norm,
        "regimen_detectado": "regular",
        "sesiones_consolidadas": 0,
        "sesiones_cruzadas_24h": 0,
        "salidas_imputadas": 0,
        "hora_cierre_diurno": "20:30",
        "hora_cierre_nocturno": None,
        "rollup_asistencia": None,
        "rollup_vehicular": None,
        "errores": [],
    }

    # 0. Inspección de reglas horarias vigentes para ayer (espacio_id_peatonal)
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_nombre = dias_map[ayer.weekday()]

    def _parse_iso_naive(val: Any) -> Optional[datetime]:
        return _parse_dt_chile_naive(val)

    horarios = await get_horarios_operacion(db, espacio_id=espacio_id_peatonal)
    reglas_rango = [
        h for h in horarios
        if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio.date() <= ayer <= h.fecha_fin.date())
    ]
    reglas_a_evaluar = reglas_rango if reglas_rango else [
        h for h in horarios if h.activo and (h.tipo_horario == "regular" or not h.fecha_inicio)
    ]
    if not reglas_a_evaluar and horarios:
        reglas_a_evaluar = [h for h in horarios if h.activo]

    tiene_campana_24h = False
    tiene_cierre_dia_siguiente = False
    hora_cierre_diurna_str = "20:30"
    hora_cierre_nocturna_str = "07:00"

    for r in reglas_a_evaluar:
        if r.es_continuo_24h or getattr(r, "tipo_horario", "") == "extendido_24h":
            tiene_campana_24h = True

        cfg_dias = None
        if r.configuracion_dias:
            if isinstance(r.configuracion_dias, dict):
                cfg_dias = r.configuracion_dias
            elif isinstance(r.configuracion_dias, str) and r.configuracion_dias.strip():
                try:
                    cfg_dias = json.loads(r.configuracion_dias)
                except Exception:
                    cfg_dias = None

        if cfg_dias and isinstance(cfg_dias, dict) and dia_nombre in cfg_dias:
            d_info = cfg_dias[dia_nombre]
            if d_info.get("cierre_dia_siguiente"):
                tiene_cierre_dia_siguiente = True
                hora_cierre_nocturna_str = d_info.get("cierre", "07:00")
            elif d_info.get("abierto", True):
                hora_cierre_diurna_str = d_info.get("cierre", r.hora_cierre or hora_cierre_diurna_str)
        else:
            if r.cierre_dia_siguiente:
                tiene_cierre_dia_siguiente = True
                hora_cierre_nocturna_str = r.hora_cierre or "07:00"
            elif r.hora_cierre and not r.es_continuo_24h:
                hora_cierre_diurna_str = r.hora_cierre

    es_regimen_nocturno = tiene_campana_24h or tiene_cierre_dia_siguiente
    resumen["regimen_detectado"] = "24h_extendido" if es_regimen_nocturno else "regular"
    resumen["hora_cierre_diurno"] = hora_cierre_diurna_str
    if es_regimen_nocturno:
        resumen["hora_cierre_nocturno"] = hora_cierre_nocturna_str

    try:
        p_d = hora_cierre_diurna_str.split(":")
        t_cierre_d = time(int(p_d[0]), int(p_d[1]))
    except Exception:
        t_cierre_d = time(20, 30)
    dt_cierre_diurno = datetime.combine(ayer, t_cierre_d)

    try:
        p_n = hora_cierre_nocturna_str.split(":")
        t_cierre_n = time(int(p_n[0]), int(p_n[1]))
    except Exception:
        t_cierre_n = time(7, 0)
    dt_cierre_nocturno = datetime.combine(dia_siguiente, t_cierre_n)

    # 1. Obtener marcajes peatonales (con soporte para ventana de madrugada en 24h y fallback local)
    raw_torniquetes: List[Dict[str, Any]] = []
    hasta_consulta = dia_siguiente if es_regimen_nocturno else ayer

    if cons_torniquetes:
      try:
        raw_torniquetes = await adaptador.obtener_marcajes_torniquetes(desde=ayer, hasta=hasta_consulta)
      except Exception as exc_api:
        logger.warning(f"[SmartCampus] API externa no respondió para {ayer}: {exc_api}. Activando fallback a base de datos.")
        resumen["errores"].append(f"Aviso API torniquetes: {str(exc_api)}")

      if not raw_torniquetes:
        try:
            t_inicio_ea = datetime.combine(ayer, time(0, 0))
            t_fin_ea = (dt_cierre_nocturno + timedelta(minutes=15)) if es_regimen_nocturno else datetime.combine(dia_siguiente, time(0, 0))
            stmt_ea = (
                select(EventoAsistencia)
                .where(
                    EventoAsistencia.espacio_id == espacio_id_peatonal,
                    EventoAsistencia.time >= t_inicio_ea,
                    EventoAsistencia.time < t_fin_ea,
                    EventoAsistencia.alerta_coherencia_fechas == False,
                    EventoAsistencia.person_id_hash.not_like("TEST_HASH%"),
                )
                .order_by(EventoAsistencia.time.asc())
            )
            res_ea = await db.execute(stmt_ea)
            filas_ea = res_ea.scalars().all()

            for ev in filas_ea:
                sentido_local = "salida" if (ev.door_salida and not ev.door_entrada) else "entrada"
                raw_torniquetes.append({
                    "fecha": ev.time.isoformat(),
                    "id_visitante": ev.person_id_hash,
                    "ya_seudonimizado": True,
                    "sentido": sentido_local,
                    "puerta": ev.door_entrada or ev.door_salida or "Torniquete",
                })
                if ev.ultima_salida and ev.ultima_salida != ev.time:
                    raw_torniquetes.append({
                        "fecha": ev.ultima_salida.isoformat(),
                        "id_visitante": ev.person_id_hash,
                        "ya_seudonimizado": True,
                        "sentido": "salida",
                        "puerta": ev.door_salida or "Torniquete",
                    })
        except Exception as exc_db:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.error(f"[SmartCampus] Error en fallback local de torniquetes: {exc_db}")
            resumen["errores"].append(f"BD local torniquetes: {str(exc_db)}")

    try:
        if raw_torniquetes:
            eventos_por_persona: Dict[str, List[Dict[str, Any]]] = {}
            for idx_ev, r in enumerate(raw_torniquetes):
                raw_id = r.get("id_visitante") or r.get("matricula") or ""
                if r.get("ya_seudonimizado") and raw_id:
                    p_hash = str(raw_id).strip()
                elif raw_id:
                    p_hash = pseudonymize_person(str(raw_id).strip())
                else:
                    p_hash = f"sin_id_{r.get('fecha', '')}_{idx_ev}"
                eventos_por_persona.setdefault(p_hash, []).append(r)

            total_ingresos = 0
            total_salidas = 0
            permanencias_lista: List[float] = []
            salidas_imputadas_conteo = 0
            sesiones_cruzadas_conteo = 0
            personas_unicas_set: Set[str] = set()

            for p_hash, eventos in eventos_por_persona.items():
                eventos.sort(key=lambda x: str(x.get("fecha", "")))

                entradas_d1: List[datetime] = []
                for e in eventos:
                    if _clasificar_sentido_smart_campus(e.get("sentido"), vehiculo=False) == "entrada":
                        dt_in_cand = _parse_iso_naive(e.get("fecha"))
                        if dt_in_cand and dt_in_cand.date() == ayer:
                            entradas_d1.append(dt_in_cand)

                if not entradas_d1:
                    continue

                dt_in = entradas_d1[0]
                total_ingresos += len(entradas_d1)
                personas_unicas_set.add(p_hash)

                limite_salida = (
                    (dt_cierre_nocturno + timedelta(minutes=15))
                    if es_regimen_nocturno
                    else (dt_cierre_diurno + timedelta(hours=2))
                )

                salidas_validas: List[datetime] = []
                for e in eventos:
                    if _clasificar_sentido_smart_campus(e.get("sentido"), vehiculo=False) == "salida":
                        dt_out_cand = _parse_iso_naive(e.get("fecha"))
                        if dt_out_cand and dt_in < dt_out_cand <= limite_salida:
                            salidas_validas.append(dt_out_cand)

                total_salidas += len(salidas_validas)

                if salidas_validas:
                    dt_out = salidas_validas[-1]
                    if dt_out > dt_in:
                        minutos = round((dt_out - dt_in).total_seconds() / 60.0, 2)
                        permanencias_lista.append(minutos)
                        if dt_out.date() > ayer:
                            sesiones_cruzadas_conteo += 1
                else:
                    es_ingreso_tardio = dt_in.time() >= time(21, 0)
                    if es_regimen_nocturno and es_ingreso_tardio:
                        dt_out = dt_cierre_nocturno
                    else:
                        dt_out = dt_cierre_diurno

                    if dt_out > dt_in:
                        minutos = round((dt_out - dt_in).total_seconds() / 60.0, 2)
                        permanencias_lista.append(minutos)
                        salidas_imputadas_conteo += 1

            mediana_perm = (
                Decimal(f"{round(float(statistics.median(permanencias_lista)), 2):.2f}")
                if permanencias_lista
                else None
            )
            personas_unicas = len(personas_unicas_set)

            stmt_rollup = select(RollupHistoricoDiario).where(
                RollupHistoricoDiario.fecha == ayer,
                RollupHistoricoDiario.espacio_id == espacio_id_peatonal,
                RollupHistoricoDiario.tipo == "asistencia",
            )
            res_r = await db.execute(stmt_rollup)
            rollup_row = res_r.scalar_one_or_none()

            if not rollup_row:
                rollup_row = RollupHistoricoDiario(
                    fecha=ayer,
                    espacio_id=espacio_id_peatonal,
                    tipo="asistencia",
                    ingresos_total=total_ingresos,
                    salidas_total=total_salidas,
                    personas_unicas=personas_unicas,
                    permanencia_mediana_min=mediana_perm,
                )
                db.add(rollup_row)
            else:
                rollup_row.ingresos_total = total_ingresos
                rollup_row.salidas_total = total_salidas
                rollup_row.personas_unicas = personas_unicas
                rollup_row.permanencia_mediana_min = mediana_perm

            await db.commit()
            resumen["sesiones_consolidadas"] = len(permanencias_lista)
            resumen["sesiones_cruzadas_24h"] = sesiones_cruzadas_conteo
            resumen["salidas_imputadas"] = salidas_imputadas_conteo
            resumen["rollup_asistencia"] = {
                "ingresos": total_ingresos,
                "salidas": total_salidas,
                "personas_unicas": personas_unicas,
                "mediana_permanencia": float(mediana_perm) if mediana_perm else None,
            }
    except Exception as exc_p:
        await db.rollback()
        logger.error(f"[SmartCampus] Error consolidando día cerrado peatonal: {exc_p}")
        resumen["errores"].append(f"Torniquetes cerrado: {str(exc_p)}")

    # 2. Consolidar Vehicular
    if cons_estacionamientos:
      try:
        raw_vehiculos: List[Dict[str, Any]] = []
        try:
            raw_vehiculos = await adaptador.obtener_pasos_estacionamientos(desde=ayer, hasta=ayer, solo_completas=True)
        except Exception as exc_v_api:
            logger.warning(f"[SmartCampus] API vehicular no respondió para {ayer}: {exc_v_api}. Fallback local.")
            resumen["errores"].append(f"Aviso API vehicular: {str(exc_v_api)}")

        if not raw_vehiculos:
            try:
                t_ini_v = datetime.combine(ayer, time(0, 0))
                t_fin_v = datetime.combine(dia_siguiente, time(0, 0))
                stmt_ev = (
                    select(EventoVehicular)
                    .where(
                        EventoVehicular.espacio_id == espacio_id_vehicular,
                        EventoVehicular.time >= t_ini_v,
                        EventoVehicular.time < t_fin_v,
                    )
                    .order_by(EventoVehicular.time.asc())
                )
                res_ev = await db.execute(stmt_ev)
                filas_ev = res_ev.scalars().all()
                for v in filas_ev:
                    raw_vehiculos.append({
                        "fecha": v.time.isoformat(),
                        "patente": v.patente_hash,
                        "sentido": v.direccion,
                    })
            except Exception as exc_v_db:
                try:
                    await db.rollback()
                except Exception:
                    pass
                logger.error(f"[SmartCampus] Error en fallback local vehicular: {exc_v_db}")
                resumen["errores"].append(f"BD local vehicular: {str(exc_v_db)}")

        if raw_vehiculos:
            v_entradas = 0
            v_salidas = 0
            patentes_unicas_set: Set[str] = set()

            for r in raw_vehiculos:
                if _clasificar_sentido_smart_campus(r.get("sentido"), vehiculo=True) == "entrada":
                    v_entradas += 1
                else:
                    v_salidas += 1

                pat = r.get("patente")
                if pat:
                    patentes_unicas_set.add(str(pat).strip().upper())

            stmt_v_rollup = select(RollupHistoricoDiario).where(
                RollupHistoricoDiario.fecha == ayer,
                RollupHistoricoDiario.espacio_id == espacio_id_vehicular,
                RollupHistoricoDiario.tipo == "vehicular",
            )
            res_vr = await db.execute(stmt_v_rollup)
            v_rollup_row = res_vr.scalar_one_or_none()

            if not v_rollup_row:
                v_rollup_row = RollupHistoricoDiario(
                    fecha=ayer,
                    espacio_id=espacio_id_vehicular,
                    tipo="vehicular",
                    ingresos_total=v_entradas,
                    salidas_total=v_salidas,
                    personas_unicas=len(patentes_unicas_set),
                    permanencia_mediana_min=None,
                )
                db.add(v_rollup_row)
            else:
                v_rollup_row.ingresos_total = v_entradas
                v_rollup_row.salidas_total = v_salidas
                v_rollup_row.personas_unicas = len(patentes_unicas_set)

            await db.commit()
            resumen["rollup_vehicular"] = {
                "ingresos": v_entradas,
                "salidas": v_salidas,
                "vehiculos_unicos": len(patentes_unicas_set),
            }
      except Exception as exc:
          await db.rollback()
          logger.error(f"[SmartCampus] Error consolidando día cerrado vehicular: {exc}")
          resumen["errores"].append(f"Estacionamientos cerrado: {str(exc)}")

    return resumen


# =============================================================================
# GESTIÓN ADMINISTRATIVA DE SECTORES Y ESTADO DE SINCRONIZACIÓN
# =============================================================================

async def obtener_resumen_estado_smart_campus(db: AsyncSession) -> Dict[str, Any]:
    """
    Retorna el estado más reciente de la sincronización de Smart Campus para torniquetes y estacionamientos.
    """
    stmt = select(EstadoSincronizacionFuente).order_by(EstadoSincronizacionFuente.ultima_ejecucion_en.desc())
    res = await db.execute(stmt)
    registros = res.scalars().all()

    items = []
    for reg in registros:
        items.append({
            "id": reg.id,
            "fuente": reg.fuente,
            "espacio_id": reg.espacio_id,
            "ultima_fecha_sincronizada": reg.ultima_fecha_sincronizada.isoformat() if reg.ultima_fecha_sincronizada else None,
            "ultima_ejecucion_en": reg.ultima_ejecucion_en.isoformat() if reg.ultima_ejecucion_en else None,
            "filas_leidas": reg.filas_leidas,
            "filas_insertadas": reg.filas_insertadas,
            "filas_duplicadas": reg.filas_duplicadas,
            "estado": reg.estado,
            "ultimo_error": reg.ultimo_error,
        })

    return {
        "conector": "Smart Campus UCT (API Gateway)",
        "url_base": getattr(settings, "SMART_CAMPUS_API_URL", "https://integrasmartcampus.uct.cl/api/lectura"),
        "fuentes": items,
        "sincronizaciones": items,
    }


async def listar_sectores_estacionamiento(db: AsyncSession) -> List[SectorEstacionamiento]:
    """Retorna los 3 sectores de estacionamiento catalogados (CSF11, CSF21, CHS01)."""
    stmt = select(SectorEstacionamiento).order_by(SectorEstacionamiento.codigo)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def actualizar_capacidad_sector(
    db: AsyncSession,
    codigo: str,
    nueva_capacidad: int,
    activo: Optional[bool] = None,
) -> SectorEstacionamiento:
    """Actualiza la capacidad máxima o estado activo de un sector vehicular y sincroniza el aforo total del recinto."""
    if nueva_capacidad <= 0:
        raise ValueError("La capacidad máxima del sector debe ser un entero positivo mayor a cero.")

    stmt = select(SectorEstacionamiento).where(SectorEstacionamiento.codigo == codigo.upper())
    res = await db.execute(stmt)
    sector = res.scalar_one_or_none()

    if not sector:
        raise ValueError(f"Sector de estacionamiento con código '{codigo}' no encontrado.")

    sector.capacidad_max = nueva_capacidad
    if activo is not None:
        sector.activo = activo

    await db.flush()

    # Sincronizar automáticamente la capacidad total de Espacio (id=2, tipo='estacionamiento')
    # con la suma de las capacidades de los sectores vehiculares activos
    stmt_sum = select(func.coalesce(func.sum(SectorEstacionamiento.capacidad_max), 0)).where(
        SectorEstacionamiento.activo == True
    )
    capacidad_total_sectores = (await db.execute(stmt_sum)).scalar() or 0

    if capacidad_total_sectores > 0:
        stmt_espacio = (
            update(Espacio)
            .where(Espacio.id == 2)
            .values(capacidad_max=capacidad_total_sectores)
        )
        await db.execute(stmt_espacio)

    await db.commit()
    await db.refresh(sector)

    # Invalidar cachés de capacidades y respuestas en memoria del módulo Estacionamiento (id=2)
    try:
        from app.services.vehicle_service import invalidar_cache_horarios_vehiculos
        from app.core.cache import invalidar_cache_por_espacio

        invalidar_cache_horarios_vehiculos(2)
        await invalidar_cache_por_espacio(2)
    except Exception as exc_cache:
        logger.warning("No se pudo invalidar caché vehicular tras actualizar capacidad de sector: %s", exc_cache)

    return sector

