import json
from datetime import datetime, time, date, timedelta
from typing import Optional, TYPE_CHECKING, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.domain.config_models import ConfiguracionEspacios, HorarioOperacion
from app.core.security_cipher import encrypt_api_key

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
            default_model="gemini-3.5-flash-lite",
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
    api_key: str,
) -> ConfiguracionEspacios:
    config = await get_configuracion_espacio(db, espacio_id)
    config.active_provider = provider.strip().lower()
    config.default_model = default_model.strip()
    if api_key and api_key.strip():
        config.encrypted_api_key = encrypt_api_key(api_key.strip())
    await db.commit()
    await db.refresh(config)
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

    # 2. Feriados oficiales: cerrado salvo campaña 24h activa para esa sala
    if es_feriado_oficial:
        if es_24h_automatico and sub_norm == "sala_2":
            return 1
        for h in reglas_activas:
            h_sub = _normalizar_subespacio(_obtener_valor_campo(h, "subespacio", "todos"))
            f_ini = _obtener_valor_campo(h, "fecha_inicio")
            f_fin = _obtener_valor_campo(h, "fecha_fin")
            if (
                h_sub in ("todos", sub_norm)
                and _obtener_valor_campo(h, "es_continuo_24h", False)
                and f_ini and f_fin and (f_ini <= dt <= f_fin)
            ):
                return 1
        return 0

    if es_24h_automatico and sub_norm == "sala_2":
        return 1

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


def es_horario_conforme(dt: datetime, horarios: list[HorarioOperacion]) -> bool:
    if not horarios:
        return True
    
    # 1. Buscar reglas específicas de rango que cubran la fecha
    reglas_rango = [
        h for h in horarios
        if h.activo and h.fecha_inicio and h.fecha_fin and (h.fecha_inicio <= dt <= h.fecha_fin)
    ]
    
    # Si existen reglas de rango activas para esa fecha, tienen prioridad
    reglas_a_evaluar = reglas_rango if reglas_rango else [
        h for h in horarios if h.activo and h.anio == dt.year
    ]
    
    if not reglas_a_evaluar:
        return True

    t = dt.time()
    dias_map = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    dia_actual = dias_map[dt.weekday()]
    
    # Si alguna de las reglas activas aplicables valida el acceso, se considera conforme
    for regla in reglas_a_evaluar:
        if regla.es_continuo_24h:
            return True

        # Verificar si la regla tiene configuración diferenciada por día
        cfg_dias = None
        if regla.configuracion_dias:
            if isinstance(regla.configuracion_dias, dict):
                cfg_dias = regla.configuracion_dias
            elif isinstance(regla.configuracion_dias, str) and regla.configuracion_dias.strip():
                try:
                    cfg_dias = json.loads(regla.configuracion_dias)
                except Exception:
                    cfg_dias = None

        if cfg_dias and isinstance(cfg_dias, dict) and dia_actual in cfg_dias:
            dia_info = cfg_dias[dia_actual]
            if not dia_info.get("abierto", True):
                # Si el día está expresamente cerrado (ej: domingo cerrado), no valida por esta regla
                continue
            
            try:
                hora_ap = dia_info.get("apertura", regla.hora_apertura)
                hora_ci = dia_info.get("cierre", regla.hora_cierre)
                h_ap, m_ap = map(int, hora_ap.split(":"))
                h_ci, m_ci = map(int, hora_ci.split(":"))
                t_apertura = time(h_ap, m_ap)
                t_cierre = time(h_ci, m_ci)
                overnight = dia_info.get("cierre_dia_siguiente", regla.cierre_dia_siguiente)

                if overnight:
                    if t >= t_apertura or t <= t_cierre:
                        return True
                else:
                    if t_apertura <= t <= t_cierre:
                        return True
            except Exception:
                return True
        else:
            # Evaluación estándar si no hay desglose por día
            try:
                h_ap, m_ap = map(int, regla.hora_apertura.split(":"))
                h_ci, m_ci = map(int, regla.hora_cierre.split(":"))
                t_apertura = time(h_ap, m_ap)
                t_cierre = time(h_ci, m_ci)
                
                if regla.cierre_dia_siguiente:
                    if t >= t_apertura or t <= t_cierre:
                        return True
                else:
                    if t_apertura <= t <= t_cierre:
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


