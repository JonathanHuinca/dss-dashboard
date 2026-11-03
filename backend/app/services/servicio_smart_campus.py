"""
servicio_smart_campus.py — Servicio de Sincronización y Procesamiento API Smart Campus UCT.

Implementa la arquitectura de Doble Pipeline:
1. Ingesta Horaria en Vivo: sincroniza eventos del día en curso de forma incremental e idempotente
   para alimentar el aforo actual (KPIs en vivo) de biblioteca y los 3 sectores de estacionamiento.
2. Consolidación Diaria Nocturna: consolida a las 00:05 horas el día cerrado (D-1), emparejando
   sesiones completas, calculando permanencias reales, imputando salidas no marcadas y actualizando rollups.
"""
import asyncio
import logging
import statistics
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

async def sincronizar_aforo_vivo_horario(
    db: AsyncSession,
    espacio_id_peatonal: int = 1,
    espacio_id_vehicular: int = 2,
    desde_manual: Optional[date] = None,
    hasta_manual: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Sincroniza de forma incremental e idempotente los eventos desde la última fecha
    registrada en la base de datos (recuperación automática de brecha) hasta hoy.
    Verifica las claves primarias existentes para no duplicar ni alterar los datos previos.
    """
    from sqlalchemy import text

    hoy = hasta_manual or datetime.now().date()
    limite_retroceso = hoy - timedelta(days=45)
    adaptador = SmartCampusAdapter()

    # Determinar fecha de inicio incremental para Biblioteca (torniquetes)
    if desde_manual:
        desde_peatonal = desde_manual
    else:
        fila_max_p = (
            await db.execute(
                text("SELECT MAX(CAST(time AS DATE)) FROM eventos_asistencia WHERE espacio_id = :espacio_id"),
                {"espacio_id": espacio_id_peatonal},
            )
        ).scalar()
        if fila_max_p and isinstance(fila_max_p, str):
            fila_max_p = date.fromisoformat(fila_max_p[:10])
        desde_peatonal = max(fila_max_p, limite_retroceso) if (fila_max_p and fila_max_p <= hoy) else hoy

    # Determinar fecha de inicio incremental para Estacionamientos (ANPR)
    if desde_manual:
        desde_vehicular = desde_manual
    else:
        fila_max_v = (
            await db.execute(
                text("SELECT MAX(CAST(time AS DATE)) FROM eventos_vehiculares WHERE espacio_id = :espacio_id"),
                {"espacio_id": espacio_id_vehicular},
            )
        ).scalar()
        if fila_max_v and isinstance(fila_max_v, str):
            fila_max_v = date.fromisoformat(fila_max_v[:10])
        desde_vehicular = max(fila_max_v, limite_retroceso) if (fila_max_v and fila_max_v <= hoy) else hoy

    resumen = {
        "fecha": hoy.isoformat(),
        "rango_torniquetes": f"{desde_peatonal.isoformat()} a {hoy.isoformat()}",
        "rango_estacionamientos": f"{desde_vehicular.isoformat()} a {hoy.isoformat()}",
        "torniquetes": {"leidos": 0, "insertados": 0, "duplicados": 0},
        "estacionamientos": {"leidos": 0, "insertados": 0, "duplicados": 0},
        "errores": [],
    }

    # 1. Sincronizar Torniquetes de Biblioteca
    try:
        raw_torniquetes = await adaptador.obtener_marcajes_torniquetes(desde=desde_peatonal, hasta=hoy)
        resumen["torniquetes"]["leidos"] = len(raw_torniquetes)

        if raw_torniquetes:
            res_existentes = await db.execute(
                text("""
                    SELECT time, person_id_hash
                    FROM eventos_asistencia
                    WHERE espacio_id = :espacio_id
                      AND CAST(time AS DATE) >= :desde
                      AND CAST(time AS DATE) <= :hasta
                """),
                {"espacio_id": espacio_id_peatonal, "desde": desde_peatonal, "hasta": hoy},
            )
            existentes_set = {(row[0], row[1]) for row in res_existentes.fetchall()}

            # Contabilizar marcajes por persona-día en el lote descargado
            conteo_persona_dia: Dict[tuple, int] = {}
            eventos_preparados = []
            for r in raw_torniquetes:
                fecha_str = r.get("fecha", "")
                if not fecha_str:
                    continue
                dt_evento = datetime.fromisoformat(fecha_str).replace(tzinfo=None)
                raw_id = r.get("matricula") or r.get("id_visitante") or ""
                if raw_id:
                    person_hash = pseudonymize_person(str(raw_id).strip())
                else:
                    person_hash = f"sin_id_{dt_evento.strftime('%Y%m%d%H%M%S')}_{r.get('puerta', 'desc')[:20]}"
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

                sentido = str(r.get("sentido", "")).lower()
                es_salida = any(s in sentido for s in ["salida", "out", "egreso"])
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
                # Enriquecer carrera y facultad desde dim_estudiante_carrera y calcular permanencia por sesión diaria
                await db.execute(
                    text("""
                        UPDATE ea
                        SET ea.carrera = dec.carr_nombre,
                            ea.facultad = CASE
                                WHEN dec.facultad IS NOT NULL AND dec.facultad <> 'Facultad UCT' THEN dec.facultad
                                ELSE COALESCE(ea.facultad, dec.facultad)
                            END
                        FROM eventos_asistencia ea
                        INNER JOIN dim_estudiante_carrera dec ON ea.person_id_hash = dec.person_id_hash
                        WHERE ea.espacio_id = :espacio_id
                          AND CAST(ea.time AS DATE) >= :desde
                    """),
                    {"espacio_id": espacio_id_peatonal, "desde": desde_peatonal},
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
    try:
        raw_estacionamientos = await adaptador.obtener_pasos_estacionamientos(
            desde=desde_vehicular,
            hasta=hoy,
            solo_completas=True,
        )
        resumen["estacionamientos"]["leidos"] = len(raw_estacionamientos)

        if raw_estacionamientos:
            res_v = await db.execute(
                text("""
                    SELECT time, patente_hash, camara
                    FROM eventos_vehiculares
                    WHERE espacio_id = :espacio_id
                      AND CAST(time AS DATE) >= :desde
                      AND CAST(time AS DATE) <= :hasta
                """),
                {"espacio_id": espacio_id_vehicular, "desde": desde_vehicular, "hasta": hoy},
            )
            v_existentes_set = {(row[0], row[1], row[2]) for row in res_v.fetchall()}

            v_insertados = 0
            v_duplicados = 0
            v_en_lote = 0

            for r in raw_estacionamientos:
                fecha_str = r.get("fecha", "")
                if not fecha_str:
                    continue
                dt_evento = datetime.fromisoformat(fecha_str).replace(tzinfo=None)

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

                sentido_raw = str(r.get("sentido", "")).lower()
                if "acercandose" in sentido_raw or "entrada" in sentido_raw:
                    direccion = "entrada"
                elif "alejandose" in sentido_raw or "salida" in sentido_raw:
                    direccion = "salida"
                else:
                    direccion = "entrada"

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

    # Invalidar cachés de recinto cuando existan nuevos datos
    await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id_peatonal)
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
) -> Dict[str, Any]:
    """
    Consolida un día completo cerrado (por defecto ayer D-1).
    Al contar con el 100% de entradas y salidas ocurridas:
    1. Empareja sesiones peatonales por persona para calcular permanencia_min exacta.
    2. Imputa salidas a estudiantes que no registraron egreso (fijando hora de cierre de biblioteca).
    3. Calcula totales y personas únicas para el rollup histórico diario.
    """
    ayer = fecha_objetivo or (datetime.now().date() - timedelta(days=1))
    adaptador = SmartCampusAdapter()

    resumen = {
        "fecha_consolidada": ayer.isoformat(),
        "sesiones_consolidadas": 0,
        "salidas_imputadas": 0,
        "rollup_asistencia": None,
        "rollup_vehicular": None,
        "errores": [],
    }

    # 1. Obtener todos los marcajes del día cerrado desde la API institucional
    try:
        raw_torniquetes = await adaptador.obtener_marcajes_torniquetes(desde=ayer, hasta=ayer)
        if raw_torniquetes:
            # Agrupar marcajes por persona
            eventos_por_persona: Dict[str, List[Dict[str, Any]]] = {}
            for r in raw_torniquetes:
                raw_id = r.get("id_visitante") or r.get("matricula") or ""
                p_hash = pseudonymize_person(str(raw_id).strip()) if raw_id else f"sin_id_{r.get('fecha', '')}"
                eventos_por_persona.setdefault(p_hash, []).append(r)

            total_ingresos = 0
            total_salidas = 0
            permanencias_lista: List[float] = []
            salidas_imputadas_conteo = 0

            # Hora límite de cierre habitual para imputación
            hora_cierre_defecto = datetime.combine(ayer, time(20, 30))

            for p_hash, eventos in eventos_por_persona.items():
                # Ordenar por fecha del evento
                eventos.sort(key=lambda x: x.get("fecha", ""))

                entradas = [e for e in eventos if any(s in str(e.get("sentido", "")).lower() for s in ["entrada", "in", "ingreso"])]
                salidas = [e for e in eventos if any(s in str(e.get("sentido", "")).lower() for s in ["salida", "out", "egreso"])]

                total_ingresos += len(entradas)
                total_salidas += len(salidas)

                if entradas and salidas:
                    dt_in = datetime.fromisoformat(entradas[0]["fecha"])
                    dt_out = datetime.fromisoformat(salidas[-1]["fecha"])
                    if dt_out > dt_in:
                        minutos = round((dt_out - dt_in).total_seconds() / 60.0, 2)
                        permanencias_lista.append(minutos)
                elif entradas and not salidas:
                    # Persona entró y nunca marcó salida: imputación con hora de cierre
                    dt_in = datetime.fromisoformat(entradas[0]["fecha"])
                    dt_out = hora_cierre_defecto
                    if dt_out > dt_in:
                        minutos = round((dt_out - dt_in).total_seconds() / 60.0, 2)
                        permanencias_lista.append(minutos)
                        salidas_imputadas_conteo += 1

            # Calcular mediana de permanencia
            mediana_perm = Decimal(round(statistics.median(permanencias_lista), 2)) if permanencias_lista else None

            # Actualizar o insertar en rollup_historico_diario
            stmt_rollup = select(RollupHistoricoDiario).where(
                RollupHistoricoDiario.fecha == ayer,
                RollupHistoricoDiario.espacio_id == espacio_id_peatonal,
                RollupHistoricoDiario.tipo == "asistencia",
            )
            res_r = await db.execute(stmt_rollup)
            rollup_row = res_r.scalar_one_or_none()

            personas_unicas = len(eventos_por_persona)

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
            resumen["sesiones_consolidadas"] = len(eventos_por_persona)
            resumen["salidas_imputadas"] = salidas_imputadas_conteo
            resumen["rollup_asistencia"] = {
                "ingresos": total_ingresos,
                "salidas": total_salidas,
                "personas_unicas": personas_unicas,
                "mediana_permanencia": float(mediana_perm) if mediana_perm else None,
            }
    except Exception as exc:
        logger.error(f"[SmartCampus] Error consolidando día cerrado peatonal: {exc}")
        resumen["errores"].append(f"Torniquetes cerrado: {str(exc)}")

    # 2. Consolidar Vehicular
    try:
        raw_vehiculos = await adaptador.obtener_pasos_estacionamientos(desde=ayer, hasta=ayer, solo_completas=True)
        if raw_vehiculos:
            v_entradas = 0
            v_salidas = 0
            patentes_unicas_set: Set[str] = set()

            for r in raw_vehiculos:
                sentido = str(r.get("sentido", "")).lower()
                if "acercandose" in sentido or "entrada" in sentido:
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
    return sector

