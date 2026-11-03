from app.services.chat.auditoria_chat import (
    registrar_auditoria_chat,
    record_chat_audit,
)
from app.services.chat.fechas_chat import (
    MONTH_NAMES,
    MONTH_MAP_ES,
    detect_months_in_text,
    obtener_anio_activo_espacio,
    extraer_o_normalizar_fechas,
    obtener_contexto_calendario_rango,
)
from app.services.chat.generadores_grafico import (
    serialize_fig,
    serialize_df,
    generate_monthly_chart,
    generate_weekly_chart,
    generate_exams_impact_chart,
    generate_peak_hours_chart,
    generate_cameras_chart,
    generate_stay_profiles_chart,
    generate_monthly_trend_chart,
)
from app.services.chat.ejecutor_herramientas import (
    ejecutar_consulta_tool,
    resolver_datos_grafico_contexto,
    _cache_resultados_herramientas,
)
from app.services.chat.exportacion_pdf import (
    generar_pdf_conversacion,
)
from app.services.chat.procesador_chat import (
    procesar_consulta_analitica,
)

__all__ = [
    "registrar_auditoria_chat",
    "record_chat_audit",
    "MONTH_NAMES",
    "MONTH_MAP_ES",
    "detect_months_in_text",
    "obtener_anio_activo_espacio",
    "extraer_o_normalizar_fechas",
    "obtener_contexto_calendario_rango",
    "serialize_fig",
    "serialize_df",
    "generate_monthly_chart",
    "generate_weekly_chart",
    "generate_exams_impact_chart",
    "generate_peak_hours_chart",
    "generate_cameras_chart",
    "generate_stay_profiles_chart",
    "generate_monthly_trend_chart",
    "ejecutar_consulta_tool",
    "resolver_datos_grafico_contexto",
    "_cache_resultados_herramientas",
    "generar_pdf_conversacion",
    "procesar_consulta_analitica",
]
