from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    prompt: str = Field(..., description="Consulta analítica del usuario en lenguaje natural", examples=["¿Cuál fue la semana de mayor congestión?"])
    dataset_tipo: str = Field("biblioteca", description="Tipo de dataset analítico ('biblioteca' o 'estacionamiento')", examples=["biblioteca"])
    session_id: str = Field(..., description="Identificador único de la sesión de interacción", examples=["session-001"])
    conversacion_id: Optional[str] = Field(None, description="Identificador único UUID de la conversación persistente")
    espacio_id: int = Field(1, description="ID del espacio (para configuración)")
    model: str = Field("gemini-2.0-flash", description="Modelo LLM a invocar", examples=["gemini-2.0-flash"])
    grafico_contexto: Optional[str] = Field(None, description="Contexto del gráfico específico desde donde se origina la consulta")
    stream: Optional[bool] = Field(False, description="Activar Server-Sent Events (SSE) streaming")
    fecha_inicio: Optional[str] = Field(None, description="Fecha de inicio del filtro actual YYYY-MM-DD")
    fecha_fin: Optional[str] = Field(None, description="Fecha de fin del filtro actual YYYY-MM-DD")
    periodo_label: Optional[str] = Field(None, description="Etiqueta legible del período actual")
    filtros: Optional[Dict[str, Any]] = Field(None, description="Filtros activos en el dashboard")


class ChatResponse(BaseModel):
    tipo: str = Field(..., description="Tipo de contenido retornado: 'component', 'plotly', 'df' o 'text'", examples=["component"])
    explicacion: str = Field(..., description="Explicación analítica y ejecutiva del resultado", examples=["Durante el mes de Marzo..."])
    component: Optional[str] = Field(None, description="Componente React institucional sugerido (ej. OccupancyAreaChart)")
    payload: Optional[Any] = Field(None, description="Datos crudos obtenidos de la base de datos")
    fig_data: Optional[Dict[str, Any]] = Field(None, description="Estructura serializada de la figura Plotly (retrocompatibilidad)")
    table_data: Optional[List[Dict[str, Any]]] = Field(None, description="Datos tabulares para representación estructurada")
    session_id: str = Field(..., description="Identificador de la sesión")
    conversacion_id: Optional[str] = Field(None, description="Identificador único UUID de la conversación persistente")
    model_used: str = Field(..., description="Modelo de IA utilizado en la inferencia")


class ConversacionCrearRequest(BaseModel):
    espacio_id: int = Field(1, description="ID del espacio asociado")
    titulo: Optional[str] = Field(None, description="Título opcional para la conversación")


class ConversacionRenombrarRequest(BaseModel):
    titulo: str = Field(..., description="Nuevo título de la conversación")


class ConversacionArchivarRequest(BaseModel):
    archivada: bool = Field(True, description="Estado de archivo")


class MensajeItemResponse(BaseModel):
    id: str
    conversacion_id: str
    rol: str
    tipo: str
    contenido: str
    herramienta: Optional[str] = None
    argumentos_json: Optional[str] = None
    modelo: Optional[str] = None
    creado_en: str


class ConversacionResumenResponse(BaseModel):
    id: str
    usuario_id: int
    espacio_id: int
    titulo: str
    creada_en: str
    actualizada_en: str
    archivada: bool


class ConversacionDetalleResponse(BaseModel):
    id: str
    usuario_id: int
    espacio_id: int
    titulo: str
    creada_en: str
    actualizada_en: str
    archivada: bool
    mensajes: List[MensajeItemResponse]


class ExportPdfRequest(BaseModel):
    session_id: str = Field(..., description="Identificador de la sesión a consolidar en PDF", examples=["session-001"])
    conversacion_id: Optional[str] = Field(None, description="Identificador único UUID de la conversación")
    espacio_id: int = Field(1, description="ID del espacio para exportación")
    titulo: Optional[str] = Field("Informe Ejecutivo Consolidado - DSS UCT", description="Título institucional del informe")
    graficos_b64: Optional[Dict[str, str]] = Field(None, description="Imágenes base64 PNG indexadas por id o clave de consulta")
    consulta_texto: Optional[str] = Field(None, description="Texto de la consulta para exportación individual")
    respuesta_texto: Optional[str] = Field(None, description="Texto de la respuesta para exportación individual")
    datos_tabla: Optional[List[Dict[str, Any]]] = Field(None, description="Filas tabulares para exportación individual")

