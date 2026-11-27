from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

ZONA_CHILE = ZoneInfo("America/Santiago")


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def ahora_chile() -> datetime:
    return datetime.now(ZONA_CHILE)


def ahora_chile_naive() -> datetime:
    return datetime.now(ZONA_CHILE).replace(tzinfo=None)


def marcar_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def utc_a_chile(dt: Optional[datetime]) -> Optional[datetime]:
    dt_utc = marcar_utc(dt)
    if dt_utc is None:
        return None
    return dt_utc.astimezone(ZONA_CHILE)


def marcar_chile(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZONA_CHILE)
    return dt.astimezone(ZONA_CHILE)


def inicio_dia_chile(referencia: Optional[datetime] = None) -> datetime:
    if referencia is None:
        base = ahora_chile()
    elif referencia.tzinfo is None:
        base = referencia.replace(tzinfo=timezone.utc).astimezone(ZONA_CHILE)
    else:
        base = referencia.astimezone(ZONA_CHILE)
    return datetime(base.year, base.month, base.day, 0, 0, 0, tzinfo=ZONA_CHILE)


def inicio_dia_chile_en_utc_naive(referencia: Optional[datetime] = None) -> datetime:
    """Retorna la medianoche de Chile expresada en UTC sin tzinfo para filtros datetime2."""
    return inicio_dia_chile(referencia).astimezone(timezone.utc).replace(tzinfo=None)
