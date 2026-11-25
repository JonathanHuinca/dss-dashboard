import json
from datetime import datetime, time, date, timedelta
from typing import Optional, TYPE_CHECKING, Any
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.config_models import (
    ConfiguracionEspacios,
    ConfiguracionSMTP,
    CredencialProveedorIA,
    HorarioOperacion,
)
from app.core.security_cipher import decrypt_api_key, encrypt_api_key, mask_api_key
from app.core.validacion_red import validar_host_smtp, validar_url_proveedor_ia

if TYPE_CHECKING:
    from app.schemas.config_schemas import HorarioOperacionCreate, HorarioOperacionUpdate


async def get_configuracion_espacio(db: AsyncSession, espacio_id: int) -> ConfiguracionEspacios:
    stmt = select(ConfiguracionEspacios).where(ConfiguracionEspacios.espacio_id == espacio_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()
    if not config:
        config = ConfiguracionEspacios(
            espacio_id=espacio_id,
            ia_asistente_activo=True,
            active_provider="gemini",
            default_model="gemini-3.1-flash-lite",
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)
    return config

async def toggle_ia_asistente(db: AsyncSession, espacio_id: int) -> ConfiguracionEspacios:
    config = await get_configuracion_espacio(db, espacio_id)
    config.ia_asistente_activo = not config.ia_asistente_activo
    await db.commit()
    await db.refresh(config)
    return config

async def update_llm_provider(
    db: AsyncSession,
    espacio_id: int,
    provider: str,
    default_model: str,
    api_key: Optional[str],
) -> ConfiguracionEspacios:
    from app.services.llm_client import limpiar_cache_clientes_llm

    config = await get_configuracion_espacio(db, espacio_id)
    config.active_provider = provider.strip().lower()
    config.default_model = default_model.strip()
    if api_key and api_key.strip():
        config.encrypted_api_key = encrypt_api_key(api_key.strip())
    await db.commit()
    await db.refresh(config)
    limpiar_cache_clientes_llm()
    return config

async def get_espacios_activos_capacidades(db: AsyncSession) -> tuple[dict, str]:
    from app.domain.models import Espacio
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        stmt = select(Espacio.tipo, Espacio.capacidad_max).where(Espacio.activo == True)
        result = await db.execute(stmt)
        espacios = result.all()
        
        if not espacios:
            return {}, "db"
            
        capacidades = {}
        for tipo, capacidad_max in espacios:
            key = "vehicular" if tipo.lower() == "estacionamiento" else tipo.lower()
            capacidades[key] = capacidad_max or 0
        return capacidades, "db"
    except Exception as e:
        logger.error(f"Error consultando capacidades activas: {e}")
        return {"biblioteca": 350, "vehicular": 180}, "fallback"


async def get_horarios_operacion(
    db: AsyncSession,
    espacio_id: Optional[int] = None,
    anio: Optional[int] = None,
    subespacio: Optional[str] = None,
) -> list[HorarioOperacion]:
    from app.domain.config_models import HorarioOperacion
    stmt = select(HorarioOperacion)
    if espacio_id is not None:
        stmt = stmt.where(HorarioOperacion.espacio_id == espacio_id)
    if anio is not None:
        stmt = stmt.where(HorarioOperacion.anio == anio)
    if subespacio is not None and subespacio != "todos":
        stmt = stmt.where(
            (HorarioOperacion.subespacio == subespacio) | 
            (HorarioOperacion.subespacio == "todos") | 
            (HorarioOperacion.subespacio == None)
        )
    stmt = stmt.order_by(HorarioOperacion.anio.desc(), HorarioOperacion.fecha_inicio.asc(), HorarioOperacion.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def create_horario_operacion(
    db: AsyncSession,
    data: "HorarioOperacionCreate",
) -> HorarioOperacion:
    from app.domain.config_models import HorarioOperacion
    dump_data = data.model_dump()
    if isinstance(dump_data.get("configuracion_dias"), dict):
        dump_data["configuracion_dias"] = json.dumps(dump_data["configuracion_dias"])
    horario = HorarioOperacion(**dump_data)
    db.add(horario)
    await db.commit()
    await db.refresh(horario)
    return horario


async def update_horario_operacion(
    db: AsyncSession,
    horario_id: int,
    data: "HorarioOperacionUpdate",
) -> Optional[HorarioOperacion]:
    from app.domain.config_models import HorarioOperacion
    stmt = select(HorarioOperacion).where(HorarioOperacion.id == horario_id)
    result = await db.execute(stmt)
    horario = result.scalar_one_or_none()
    if not horario:
        return None
    dump_data = data.model_dump(exclude_unset=True)
    if "configuracion_dias" in dump_data and isinstance(dump_data["configuracion_dias"], dict):
        dump_data["configuracion_dias"] = json.dumps(dump_data["configuracion_dias"])

    # Versionado histórico automático cuando cambia un horario habitual vigente desde días anteriores
    hoy = datetime.now().date()
    ayer_fin = datetime.combine(hoy - timedelta(days=1), time(23, 59, 59))
    hoy_inicio = datetime.combine(hoy, time(0, 0, 0))

    campos_horario = ("hora_apertura", "hora_cierre", "configuracion_dias", "es_continuo_24h", "cierre_dia_siguiente")
    cambio_estructural = any(
        k in dump_data and dump_data[k] != getattr(horario, k)
        for k in campos_horario
    )
    inicio_previo = horario.fecha_inicio.date() if horario.fecha_inicio else date(horario.anio, 1, 1)

    if (
        horario.tipo_horario == "regular"
        and horario.fecha_fin is None
        and cambio_estructural
        and inicio_previo < hoy
    ):
        copia_historica = HorarioOperacion(
            espacio_id=horario.espacio_id,
            subespacio=horario.subespacio or "todos",
            anio=horario.anio,
            tipo_horario="historico_regular",
            fecha_inicio=horario.fecha_inicio or datetime(horario.anio, 1, 1, 0, 0, 0),
            fecha_fin=ayer_fin,
            hora_apertura=horario.hora_apertura,
            hora_cierre=horario.hora_cierre,
            cierre_dia_siguiente=horario.cierre_dia_siguiente,
            es_continuo_24h=horario.es_continuo_24h,
            configuracion_dias=horario.configuracion_dias,
            descripcion=f"{horario.descripcion or 'Horario Habitual'} (Histórico hasta {(hoy - timedelta(days=1)).strftime('%d-%m-%Y')})",
            activo=True,
        )
        db.add(copia_historica)
        if "fecha_inicio" not in dump_data or dump_data["fecha_inicio"] is None:
            dump_data["fecha_inicio"] = hoy_inicio

    for field, value in dump_data.items():
        setattr(horario, field, value)
    await db.commit()
    await db.refresh(horario)
    return horario


def _obtener_valor_campo(obj: Any, campo: str, por_defecto: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(campo, por_defecto)
    return getattr(obj, campo, por_defecto)


def _normalizar_subespacio(subespacio: Optional[str]) -> str:
    if not subespacio:
        return "todos"
    s = subespacio.strip().lower()
    if s in ("sala1", "sala_1", "csf02"):
        return "sala_1"
    if s in ("sala2", "sala_2", "csf04"):
        return "sala_2"
    if s in ("csf11", "csf21", "chs01"):
        return s.upper()
    if s in ("todas", "todos", "global", "biblioteca", "vehicular"):
        return "todos"
    return subespacio.strip()


def _evaluar_regla_individual(dt: datetime, regla: Any) -> bool:
    cfg_dias = _obtener_valor_campo(regla, "configuracion_dias")
    if cfg_dias:
        if isinstance(cfg_dias, str) and cfg_dias.strip():
            try:
                cfg_dias = json.loads(cfg_dias)
            except Exception:
                cfg_dias = None

    t = dt.time()
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_actual = dias_map[dt.weekday()]
    dia_anterior = dias_map[(dt.weekday() - 1) % 7]

    hora_ap_def = _obtener_valor_campo(regla, "hora_apertura", "08:30") or "08:30"
    hora_ci_def = _obtener_valor_campo(regla, "hora_cierre", "20:30") or "20:30"
    overnight_def = bool(_obtener_valor_campo(regla, "cierre_dia_siguiente", False))

    if isinstance(cfg_dias, dict):
        # 1. Turno de ayer que cruzó la medianoche y sigue abierto durante la madrugada de hoy
        if dia_anterior in cfg_dias:
            ayer_info = cfg_dias[dia_anterior]
            if ayer_info.get("abierto", True) and ayer_info.get("cierre_dia_siguiente", False):
                ayer_ci = ayer_info.get("cierre", hora_ci_def) or hora_ci_def
                try:
                    h_ci, m_ci = map(int, str(ayer_ci).split(":")[:2])
                    if t <= time(h_ci, m_ci):
                        return True
                except Exception:
                    pass

        # 2. Turno programado para el día de hoy
        if dia_actual in cfg_dias:
            hoy_info = cfg_dias[dia_actual]
            if not hoy_info.get("abierto", True):
                return False
            hora_ap = hoy_info.get("apertura", hora_ap_def) or hora_ap_def
            hora_ci = hoy_info.get("cierre", hora_ci_def) or hora_ci_def
            overnight = bool(hoy_info.get("cierre_dia_siguiente", overnight_def))
            try:
                h_ap, m_ap = map(int, str(hora_ap).split(":")[:2])
                h_ci, m_ci = map(int, str(hora_ci).split(":")[:2])
                t_ap = time(h_ap, m_ap)
                t_ci = time(h_ci, m_ci)
                if overnight:
                    return bool(t >= t_ap)
                return bool(t_ap <= t <= t_ci)
            except Exception:
                return True
        return False

    if _obtener_valor_campo(regla, "es_continuo_24h", False):
        return True

    try:
        h_ap, m_ap = map(int, str(hora_ap_def).split(":")[:2])
        h_ci, m_ci = map(int, str(hora_ci_def).split(":")[:2])
        t_apertura = time(h_ap, m_ap)
        t_cierre = time(h_ci, m_ci)
        if overnight_def:
            return bool(t >= t_apertura or t <= t_cierre)
        return bool(t_apertura <= t <= t_cierre)
    except Exception:
        return True


def evaluar_horario_abierto_subespacio(
    dt: datetime,
    espacio_id: int,
    subespacio: str,
    horarios: list[Any],
    contingencias: Optional[list[Any]] = None,
    es_feriado_oficial: bool = False,
    es_24h_automatico: bool = False,
) -> int:
    """
    Evalúa jerárquicamente si un subespacio ('sala_1', 'sala_2', 'CSF11', 'todos')
    está operativo (1) o cerrado/suspendido (0) en la fecha y hora indicada.
    """
    sub_norm = _normalizar_subespacio(subespacio)

    # En Biblioteca global ('todos'), está abierto si Sala 1 o Sala 2 está abierta
    if espacio_id == 1 and sub_norm == "todos":
        abierto_s1 = evaluar_horario_abierto_subespacio(
            dt, espacio_id, "sala_1", horarios, contingencias, es_feriado_oficial, False
        )
        abierto_s2 = evaluar_horario_abierto_subespacio(
            dt, espacio_id, "sala_2", horarios, contingencias, es_feriado_oficial, es_24h_automatico
        )
        return 1 if (abierto_s1 == 1 or abierto_s2 == 1) else 0

    # En Estacionamiento global ('todos'), si solo hay horarios por sector específico está abierto si al menos uno opera
    if espacio_id == 2 and sub_norm == "todos":
        reglas_veh_activas = [
            h for h in (horarios or [])
            if _obtener_valor_campo(h, "activo", True)
            and int(_obtener_valor_campo(h, "espacio_id", espacio_id) or espacio_id) == 2
        ]
        tiene_regla_todos = any(
            _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos")) == "todos"
            for h in reglas_veh_activas
        )
        subespacios_veh = sorted({
            _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos"))
            for h in reglas_veh_activas
            if _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos")) != "todos"
        })
        if not tiene_regla_todos and subespacios_veh:
            return 1 if any(
                evaluar_horario_abierto_subespacio(
                    dt, espacio_id, sub_veh, horarios, contingencias, es_feriado_oficial, False
                ) == 1
                for sub_veh in subespacios_veh
            ) else 0

    fecha_dt = dt.date()
    hora_dt = dt.time()

    # 1. Prioridad Máxima: Contingencias y suspensiones puntuales por sala/sector o globales
    if contingencias:
        for c in contingencias:
            if not _obtener_valor_campo(c, "implica_cierre_total", False):
                continue
            c_espacio = _obtener_valor_campo(c, "espacio_id")
            if c_espacio is not None and int(c_espacio) != int(espacio_id):
                continue
            c_sub = _normalizar_subespacio(_obtener_valor_campo(c, "subespacio", "todos"))
            if c_sub not in ("todos", sub_norm):
                continue

            f_ini = _obtener_valor_campo(c, "fecha_inicio")
            f_fin = _obtener_valor_campo(c, "fecha_fin")
            if isinstance(f_ini, datetime):
                f_ini = f_ini.date()
            if isinstance(f_fin, datetime):
                f_fin = f_fin.date()
            if f_ini and f_fin and not (f_ini <= fecha_dt <= f_fin):
                continue

            h_ini_str = _obtener_valor_campo(c, "hora_inicio")
            h_fin_str = _obtener_valor_campo(c, "hora_fin")
            if h_ini_str and h_fin_str:
                try:
                    hi_h, hi_m = map(int, str(h_ini_str).split(":")[:2])
                    hf_h, hf_m = map(int, str(h_fin_str).split(":")[:2])
                    if time(hi_h, hi_m) <= hora_dt <= time(hf_h, hf_m):
                        return 0
                except Exception:
                    return 0
            else:
                return 0

    # Filtrar reglas activas del espacio
    reglas_activas = [
        h for h in (horarios or [])
        if _obtener_valor_campo(h, "activo", True)
        and int(_obtener_valor_campo(h, "espacio_id", espacio_id) or espacio_id) == int(espacio_id)
    ]

    es_24h_auto_valido = (
        es_24h_automatico
        and sub_norm == "sala_2"
        and (dt.weekday() < 5 or (dt.weekday() == 5 and dt.hour < 6))
    )

    # 2. Feriados oficiales: cerrado salvo campaña 24h activa para esa sala
    if es_feriado_oficial:
        reglas_24h = []
        for h in reglas_activas:
            h_sub = _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos"))
            f_ini = _obtener_valor_campo(h, "fecha_inicio")
            f_fin = _obtener_valor_campo(h, "fecha_fin")
            if (
                h_sub in ("todos", sub_norm)
                and _obtener_valor_campo(h, "es_continuo_24h", False)
                and f_ini and f_fin and (f_ini <= dt <= f_fin)
            ):
                reglas_24h.append(h)
        if reglas_24h:
            return 1 if any(_evaluar_regla_individual(dt, r) for r in reglas_24h) else 0
        if es_24h_auto_valido:
            return 1
        return 0

    # 3. Reglas temporales por rango (ej. cambio horario mensual en Sala 2 o campaña exámenes)
    reglas_rango_especificas = []
    reglas_rango_generales = []
    for h in reglas_activas:
        tipo_h = str(_obtener_valor_campo(h, "tipo_horario", "regular") or "regular")
        if tipo_h in ("regular", "historico_regular"):
            continue
        f_ini = _obtener_valor_campo(h, "fecha_inicio")
        f_fin = _obtener_valor_campo(h, "fecha_fin")
        if f_ini and f_fin and (f_ini <= dt <= f_fin):
            h_sub = _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos"))
            if h_sub == sub_norm:
                reglas_rango_especificas.append(h)
            elif h_sub == "todos":
                reglas_rango_generales.append(h)

    reglas_rango = reglas_rango_especificas if reglas_rango_especificas else reglas_rango_generales
    if reglas_rango:
        return 1 if any(_evaluar_regla_individual(dt, r) for r in reglas_rango) else 0

    if es_24h_auto_valido:
        return 1

    # 4. Reglas habituales vigentes o históricas cerradas (regular / historico_regular)
    reglas_base_especificas = []
    reglas_base_generales = []
    for h in reglas_activas:
        tipo_h = str(_obtener_valor_campo(h, "tipo_horario", "regular") or "regular")
        if tipo_h not in ("regular", "historico_regular"):
            continue
        f_ini = _obtener_valor_campo(h, "fecha_inicio")
        f_fin = _obtener_valor_campo(h, "fecha_fin")
        anio_h = _obtener_valor_campo(h, "anio", dt.year)

        vigente = False
        if f_ini and f_fin:
            vigente = bool(f_ini <= dt <= f_fin)
        elif f_ini and not f_fin:
            vigente = bool(dt >= f_ini and int(anio_h) == dt.year)
        elif not f_ini and f_fin:
            vigente = bool(dt <= f_fin and int(anio_h) == dt.year)
        else:
            vigente = bool(int(anio_h) == dt.year)

        if vigente:
            h_sub = _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos"))
            if h_sub == sub_norm:
                reglas_base_especificas.append(h)
            elif h_sub == "todos":
                reglas_base_generales.append(h)

    reglas_base = reglas_base_especificas if reglas_base_especificas else reglas_base_generales
    if reglas_base:
        return 1 if any(_evaluar_regla_individual(dt, r) for r in reglas_base) else 0

    # 5. Fallback determinista institucional si no existen reglas configuradas para ese año
    dow = dt.weekday()
    if dow == 6:
        return 0
    hr = dt.hour
    if dow == 5:
        return 1 if (10 <= hr <= 13) else 0
    if dow == 4:
        return 1 if (8 <= hr <= 19) else 0
    return 1 if (8 <= hr <= 20) else 0


async def delete_horario_operacion(
    db: AsyncSession,
    horario_id: int,
) -> bool:
    from app.domain.config_models import HorarioOperacion
    stmt = select(HorarioOperacion).where(HorarioOperacion.id == horario_id)
    result = await db.execute(stmt)
    horario = result.scalar_one_or_none()
    if not horario:
        return False
    await db.delete(horario)
    await db.commit()
    return True


def _sumar_minutos_time(t_base: time, minutos: int) -> time:
    if minutos <= 0:
        return t_base
    total_min = t_base.hour * 60 + t_base.minute + minutos
    if total_min >= 23 * 60 + 59:
        return time(23, 59, 59)
    return time(total_min // 60, total_min % 60, t_base.second)


def es_horario_conforme(
    dt: datetime,
    horarios: list[HorarioOperacion],
    subespacio: Optional[str] = None,
    es_salida: bool = False,
    tolerancia_salida_min: int = 0,
) -> bool:
    if not horarios:
        return True

    activas = [h for h in horarios if _obtener_valor_campo(h, "activo", True)]
    if not activas:
        return True

    if subespacio is not None:
        sub_norm = _normalizar_subespacio(subespacio)
        if sub_norm != "todos":
            filtradas_sub = [
                h for h in activas
                if _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos")) in (sub_norm, "todos")
            ]
            if filtradas_sub:
                activas = filtradas_sub

    # 1. Reglas especiales por rango vigentes en dt (ej. campañas 24h)
    reglas_rango = [
        h for h in activas
        if (_obtener_valor_campo(h, "tipo_horario", "regular") or "regular") not in ("regular", "historico_regular")
        and _obtener_valor_campo(h, "fecha_inicio")
        and _obtener_valor_campo(h, "fecha_fin")
        and (_obtener_valor_campo(h, "fecha_inicio") <= dt <= _obtener_valor_campo(h, "fecha_fin"))
    ]

    # 2. Reglas habituales vigentes o históricas aplicables a dt
    reglas_vigentes = []
    for h in activas:
        tipo_h = _obtener_valor_campo(h, "tipo_horario", "regular") or "regular"
        if tipo_h not in ("regular", "historico_regular"):
            continue
        f_ini = _obtener_valor_campo(h, "fecha_inicio")
        f_fin = _obtener_valor_campo(h, "fecha_fin")
        if f_ini and dt < f_ini:
            continue
        if f_fin and dt > f_fin:
            continue
        if not (f_ini and f_fin) and _obtener_valor_campo(h, "anio") != dt.year:
            continue
        reglas_vigentes.append(h)

    if reglas_rango:
        reglas_a_evaluar = reglas_rango + reglas_vigentes
    elif reglas_vigentes:
        reglas_a_evaluar = reglas_vigentes
    else:
        reglas_a_evaluar = [
            h for h in activas
            if (_obtener_valor_campo(h, "tipo_horario", "regular") or "regular") in ("regular", "historico_regular")
            and not _obtener_valor_campo(h, "fecha_fin")
        ] or activas

    if not reglas_a_evaluar:
        return True

    t = dt.time()
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_actual = dias_map[dt.weekday()]
    tolerancia_eff = tolerancia_salida_min if (es_salida and tolerancia_salida_min > 0) else 0

    # Si alguna regla aplicable valida el marcaje, se considera conforme
    for regla in reglas_a_evaluar:
        if _obtener_valor_campo(regla, "es_continuo_24h", False):
            return True

        cfg_dias = None
        raw_cfg = _obtener_valor_campo(regla, "configuracion_dias")
        if raw_cfg:
            if isinstance(raw_cfg, dict):
                cfg_dias = raw_cfg
            elif isinstance(raw_cfg, str) and raw_cfg.strip():
                try:
                    cfg_dias = json.loads(raw_cfg)
                except Exception:
                    cfg_dias = None

        h_ap_def = _obtener_valor_campo(regla, "hora_apertura", "08:30") or "08:30"
        h_ci_def = _obtener_valor_campo(regla, "hora_cierre", "20:30") or "20:30"
        ovn_def = bool(_obtener_valor_campo(regla, "cierre_dia_siguiente", False))

        if cfg_dias and isinstance(cfg_dias, dict) and dia_actual in cfg_dias:
            dia_info = cfg_dias[dia_actual]
            if not dia_info.get("abierto", True):
                continue

            try:
                hora_ap = dia_info.get("apertura", h_ap_def) or h_ap_def
                hora_ci = dia_info.get("cierre", h_ci_def) or h_ci_def
                h_ap, m_ap = map(int, str(hora_ap).split(":")[:2])
                h_ci, m_ci = map(int, str(hora_ci).split(":")[:2])
                t_apertura = time(h_ap, m_ap)
                t_cierre = _sumar_minutos_time(time(h_ci, m_ci), tolerancia_eff)
                overnight = bool(dia_info.get("cierre_dia_siguiente", ovn_def))

                if overnight:
                    if t >= t_apertura or t <= t_cierre:
                        return True
                elif t_apertura <= t <= t_cierre:
                    return True
            except Exception:
                return True
        else:
            try:
                h_ap, m_ap = map(int, str(h_ap_def).split(":")[:2])
                h_ci, m_ci = map(int, str(h_ci_def).split(":")[:2])
                t_apertura = time(h_ap, m_ap)
                t_cierre = _sumar_minutos_time(time(h_ci, m_ci), tolerancia_eff)

                if ovn_def:
                    if t >= t_apertura or t <= t_cierre:
                        return True
                elif t_apertura <= t <= t_cierre:
                    return True
            except Exception:
                return True

    return False


async def get_espacios(db: AsyncSession) -> list:
    from app.domain.models import Espacio
    stmt = select(Espacio).where(Espacio.activo == True).order_by(Espacio.id.asc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_espacio_by_id(db: AsyncSession, espacio_id: int):
    from app.domain.models import Espacio
    stmt = select(Espacio).where(Espacio.id == espacio_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_espacio_capacidad(db: AsyncSession, espacio_id: int, nueva_capacidad: int):
    from app.domain.models import Espacio
    espacio = await get_espacio_by_id(db, espacio_id)
    if not espacio:
        return None
    espacio.capacidad_max = nueva_capacidad
    await db.commit()
    await db.refresh(espacio)
    return espacio


# ---------------------------------------------------------------------------
# Gestión Multi-Proveedor de Credenciales IA
# ---------------------------------------------------------------------------
def _validar_datos_proveedor_ia(
    provider_id: str,
    base_url: Optional[str],
    api_key: Optional[str],
    requiere_key_en_alta: bool = True,
) -> tuple[str, Optional[str]]:
    from app.services.llm_client import CATALOGO_PROVEEDORES_IA

    pid = (provider_id or "").strip().lower()
    meta = CATALOGO_PROVEEDORES_IA.get(pid)
    if not meta:
        raise ValueError(f"Proveedor de IA '{pid}' no soportado.")

    url_limpia = (base_url or "").strip() or None
    if meta.get("requires_base_url") and not url_limpia:
        raise ValueError("Este proveedor requiere especificar la URL base del endpoint.")

    if url_limpia:
        url_limpia = validar_url_proveedor_ia(url_limpia, permitir_local=bool(meta.get("allows_local_http")))
    elif meta.get("default_base_url"):
        url_limpia = meta["default_base_url"]

    if requiere_key_en_alta and meta.get("requires_api_key", True):
        if not api_key or not api_key.strip():
            raise ValueError(f"El proveedor '{meta['nombre']}' requiere ingresar una API Key.")

    return pid, url_limpia


async def listar_credenciales_ia(db: AsyncSession) -> list[CredencialProveedorIA]:
    stmt = select(CredencialProveedorIA).order_by(
        CredencialProveedorIA.es_activa.desc(),
        CredencialProveedorIA.updated_at.desc(),
        CredencialProveedorIA.id.desc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def obtener_credencial_ia(db: AsyncSession, cred_id: int) -> Optional[CredencialProveedorIA]:
    stmt = select(CredencialProveedorIA).where(CredencialProveedorIA.id == cred_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _sincronizar_espacio_con_credencial(
    db: AsyncSession, provider_id: str, modelo: str
) -> None:
    await db.execute(
        sql_update(ConfiguracionEspacios).values(
            active_provider=provider_id,
            default_model=modelo,
        )
    )


async def crear_credencial_ia(
    db: AsyncSession,
    nombre: str,
    provider_id: str,
    modelo: str,
    base_url: Optional[str],
    api_key: Optional[str],
    activar: bool,
    usuario_id: Optional[int],
) -> CredencialProveedorIA:
    from app.services.llm_client import limpiar_cache_clientes_llm

    pid, url_validada = _validar_datos_proveedor_ia(provider_id, base_url, api_key, requiere_key_en_alta=True)
    modelo_limpio = modelo.strip()
    if not modelo_limpio:
        raise ValueError("Debe especificar un identificador de modelo válido.")

    plain_key = (api_key or "").strip()
    encrypted = encrypt_api_key(plain_key) if plain_key else None
    hint = mask_api_key(plain_key) if plain_key else "Sin clave"

    if activar:
        await db.execute(sql_update(CredencialProveedorIA).values(es_activa=False))
        await _sincronizar_espacio_con_credencial(db, pid, modelo_limpio)

    cred = CredencialProveedorIA(
        nombre=nombre.strip(),
        provider_id=pid,
        modelo=modelo_limpio,
        base_url=url_validada,
        encrypted_api_key=encrypted,
        key_hint=hint,
        es_activa=bool(activar),
        creado_por_id=usuario_id,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    limpiar_cache_clientes_llm()
    return cred


async def actualizar_credencial_ia(
    db: AsyncSession,
    cred: CredencialProveedorIA,
    nombre: Optional[str] = None,
    provider_id: Optional[str] = None,
    modelo: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> CredencialProveedorIA:
    from app.services.llm_client import limpiar_cache_clientes_llm

    pid_nuevo = (provider_id or cred.provider_id).strip().lower()
    if base_url is not None:
        url_objetivo = base_url.strip() or None
    elif pid_nuevo != cred.provider_id:
        url_objetivo = None
    else:
        url_objetivo = cred.base_url
    tiene_clave = bool(cred.encrypted_api_key) or bool(api_key and api_key.strip())
    pid_validado, url_validada = _validar_datos_proveedor_ia(
        pid_nuevo,
        url_objetivo,
        api_key,
        requiere_key_en_alta=not tiene_clave,
    )

    if nombre is not None:
        cred.nombre = nombre.strip()
    cred.provider_id = pid_validado
    cred.base_url = url_validada
    if modelo is not None:
        if not modelo.strip():
            raise ValueError("El modelo no puede estar vacío.")
        cred.modelo = modelo.strip()
    if api_key is not None and api_key.strip():
        plain_key = api_key.strip()
        cred.encrypted_api_key = encrypt_api_key(plain_key)
        cred.key_hint = mask_api_key(plain_key)

    if cred.es_activa:
        await _sincronizar_espacio_con_credencial(db, cred.provider_id, cred.modelo)

    await db.commit()
    await db.refresh(cred)
    limpiar_cache_clientes_llm()
    return cred


async def activar_credencial_ia(db: AsyncSession, cred: CredencialProveedorIA) -> CredencialProveedorIA:
    from app.services.llm_client import limpiar_cache_clientes_llm

    await db.execute(sql_update(CredencialProveedorIA).values(es_activa=False))
    cred.es_activa = True
    await _sincronizar_espacio_con_credencial(db, cred.provider_id, cred.modelo)
    await db.commit()
    await db.refresh(cred)
    limpiar_cache_clientes_llm()
    return cred


async def probar_credencial_ia_guardada(db: AsyncSession, cred: CredencialProveedorIA) -> dict:
    from app.services.llm_client import CATALOGO_PROVEEDORES_IA, probar_cliente_llm

    meta = CATALOGO_PROVEEDORES_IA.get(cred.provider_id, {})
    plain_key = decrypt_api_key(cred.encrypted_api_key) if cred.encrypted_api_key else ""
    if meta.get("requires_api_key", True) and not plain_key:
        res = {
            "ok": False,
            "latencia_ms": 0.0,
            "mensaje": "La credencial no tiene una API Key válida almacenada.",
            "provider_id": cred.provider_id,
            "modelo": cred.modelo,
        }
    else:
        res = await probar_cliente_llm(cred.provider_id, plain_key, cred.modelo, cred.base_url)

    cred.ultimo_test_ok = bool(res["ok"])
    cred.ultimo_test_en = datetime.utcnow()
    await db.commit()
    await db.refresh(cred)
    return res


async def eliminar_credencial_ia(db: AsyncSession, cred: CredencialProveedorIA) -> None:
    from app.services.llm_client import limpiar_cache_clientes_llm

    era_activa = cred.es_activa
    await db.delete(cred)
    if era_activa:
        await _sincronizar_espacio_con_credencial(db, "gemini", "gemini-3.1-flash-lite")
    await db.commit()
    limpiar_cache_clientes_llm()


# ---------------------------------------------------------------------------
# Gestión Segura de Perfiles SMTP Institucionales
# ---------------------------------------------------------------------------
def _normalizar_cifrado_smtp(use_tls: bool, use_ssl: bool, port: int) -> tuple[bool, bool]:
    if use_ssl or (port == 465 and not use_tls):
        return False, True
    if use_tls:
        return True, False
    return False, False


async def listar_configuraciones_smtp(db: AsyncSession) -> list[ConfiguracionSMTP]:
    stmt = select(ConfiguracionSMTP).order_by(
        ConfiguracionSMTP.es_activa.desc(),
        ConfiguracionSMTP.updated_at.desc(),
        ConfiguracionSMTP.id.desc(),
    )
    return list((await db.execute(stmt)).scalars().all())


async def obtener_configuracion_smtp(db: AsyncSession, smtp_id: int) -> Optional[ConfiguracionSMTP]:
    stmt = select(ConfiguracionSMTP).where(ConfiguracionSMTP.id == smtp_id)
    return (await db.execute(stmt)).scalar_one_or_none()


async def crear_configuracion_smtp(
    db: AsyncSession,
    nombre: str,
    host: str,
    port: int,
    use_tls: bool,
    use_ssl: bool,
    username: str,
    from_email: str,
    from_name: str,
    password: str,
    activar: bool,
    usuario_id: Optional[int],
) -> ConfiguracionSMTP:
    from app.services.email_service import limpiar_cache_smtp

    host_ok, port_ok = validar_host_smtp(host, port)
    tls_ok, ssl_ok = _normalizar_cifrado_smtp(use_tls, use_ssl, port_ok)
    pwd_limpia = (password or "").strip()
    if not pwd_limpia:
        raise ValueError("La contraseña SMTP es obligatoria.")

    if activar:
        await db.execute(sql_update(ConfiguracionSMTP).values(es_activa=False))

    cfg = ConfiguracionSMTP(
        nombre=nombre.strip(),
        host=host_ok,
        port=port_ok,
        use_tls=tls_ok,
        use_ssl=ssl_ok,
        username=username.strip(),
        from_email=from_email.strip(),
        from_name=from_name.strip(),
        encrypted_password=encrypt_api_key(pwd_limpia),
        password_hint=mask_api_key(pwd_limpia),
        es_activa=bool(activar),
        creado_por_id=usuario_id,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    limpiar_cache_smtp()
    return cfg


async def actualizar_configuracion_smtp(
    db: AsyncSession,
    cfg: ConfiguracionSMTP,
    nombre: Optional[str] = None,
    host: Optional[str] = None,
    port: Optional[int] = None,
    use_tls: Optional[bool] = None,
    use_ssl: Optional[bool] = None,
    username: Optional[str] = None,
    from_email: Optional[str] = None,
    from_name: Optional[str] = None,
    password: Optional[str] = None,
) -> ConfiguracionSMTP:
    from app.services.email_service import limpiar_cache_smtp

    host_obj = cfg.host if host is None else host
    port_obj = cfg.port if port is None else port
    host_ok, port_ok = validar_host_smtp(host_obj, port_obj)

    tls_obj = cfg.use_tls if use_tls is None else use_tls
    ssl_obj = cfg.use_ssl if use_ssl is None else use_ssl
    if use_ssl is True and use_tls is None:
        tls_obj = False
    elif use_tls is True and use_ssl is None:
        ssl_obj = False
    tls_ok, ssl_ok = _normalizar_cifrado_smtp(tls_obj, ssl_obj, port_ok)

    if nombre is not None:
        cfg.nombre = nombre.strip()
    cfg.host = host_ok
    cfg.port = port_ok
    cfg.use_tls = tls_ok
    cfg.use_ssl = ssl_ok
    if username is not None:
        cfg.username = username.strip()
    if from_email is not None:
        cfg.from_email = from_email.strip()
    if from_name is not None:
        cfg.from_name = from_name.strip()
    if password is not None and password.strip():
        pwd_limpia = password.strip()
        cfg.encrypted_password = encrypt_api_key(pwd_limpia)
        cfg.password_hint = mask_api_key(pwd_limpia)

    await db.commit()
    await db.refresh(cfg)
    limpiar_cache_smtp()
    return cfg


async def activar_configuracion_smtp(db: AsyncSession, cfg: ConfiguracionSMTP) -> ConfiguracionSMTP:
    from app.services.email_service import limpiar_cache_smtp

    await db.execute(sql_update(ConfiguracionSMTP).values(es_activa=False))
    cfg.es_activa = True
    await db.commit()
    await db.refresh(cfg)
    limpiar_cache_smtp()
    return cfg


async def probar_configuracion_smtp_guardada(
    db: AsyncSession, cfg: ConfiguracionSMTP, destinatario: str
) -> tuple[bool, str]:
    from app.services.email_service import probar_envio_smtp

    pwd = decrypt_api_key(cfg.encrypted_password)
    datos = {
        "nombre": cfg.nombre,
        "host": cfg.host,
        "port": int(cfg.port),
        "use_tls": bool(cfg.use_tls),
        "use_ssl": bool(cfg.use_ssl),
        "username": cfg.username,
        "password": pwd,
        "from_email": cfg.from_email,
        "from_name": cfg.from_name,
    }
    ok, msg = await probar_envio_smtp(datos, destinatario)
    cfg.ultimo_test_ok = bool(ok)
    cfg.ultimo_test_en = datetime.utcnow()
    await db.commit()
    await db.refresh(cfg)
    return ok, msg


async def eliminar_configuracion_smtp(db: AsyncSession, cfg: ConfiguracionSMTP) -> None:
    from app.services.email_service import limpiar_cache_smtp

    await db.delete(cfg)
    await db.commit()
    limpiar_cache_smtp()


