"""Utilidades de sanitización para exportaciones CSV seguras."""
from typing import Any

_PREFIJOS_FORMULA_CSV = ("=", "+", "-", "@", "\t", "\r")


def sanitizar_celda_csv(valor: Any) -> Any:
    """Neutraliza inyección de fórmulas Excel/LibreOffice en celdas CSV."""
    if not isinstance(valor, str) or not valor:
        return valor
    if valor[0] in _PREFIJOS_FORMULA_CSV:
        return f"'{valor}"
    return valor
