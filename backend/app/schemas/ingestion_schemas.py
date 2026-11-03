"""
ingestion_schemas.py — Esquemas Pydantic para el módulo de Ingesta Inteligente (RF03, RF04, RF30).
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class SchemaFieldMapping(BaseModel):
    """Mapeo individual de un campo objetivo con una columna detectada del archivo."""
    target_field: str = Field(..., description="Nombre del campo requerido o estándar en el modelo de dominio")
    matched_column: Optional[str] = Field(None, description="Nombre de la columna en el archivo subido que coincide")
    status: Literal["verde", "amarillo", "rojo"] = Field(..., description="Estado del semáforo: verde (exacto), amarillo (sinónimo), rojo (faltante)")
    required: bool = Field(True, description="Indica si el campo es obligatorio para completar la ingesta")
    description: Optional[str] = Field(None, description="Descripción técnica o propósito del campo")
    classification: Optional[str] = Field("analitico", description="analitico, seudonimizar (Ley 21.719), purgar")


class FileInspectionResponse(BaseModel):
    """Respuesta estructurada del análisis e inspección previa de archivo (RF03)."""
    filename: str = Field(..., description="Nombre original del archivo analizado")
    tipo: str = Field(..., description="Contexto o módulo seleccionado (asistencia, vehicular, academico, curricular, custom)")
    espacio_id: int = Field(1, description="ID del espacio asignado")
    header_row_index: int = Field(0, description="Índice de la fila identificada como cabecera real (0-indexed)")
    total_rows_estimated: int = Field(0, description="Cantidad estimada de filas con datos en el archivo")
    columns_detected: List[str] = Field(default_factory=list, description="Lista de encabezados encontrados en el archivo")
    schema_mapping: List[SchemaFieldMapping] = Field(default_factory=list, description="Matriz de Schema Matching con semáforo")
    preview_rows: List[Dict[str, Any]] = Field(default_factory=list, description="Muestra de las primeras 5 filas sanitizadas sin PII")
    all_required_matched: bool = Field(..., description="Verdadero si todos los campos obligatorios fueron vinculados")
    missing_required_fields: List[str] = Field(default_factory=list, description="Lista de campos obligatorios no encontrados")


class IngestionValidationResponse(BaseModel):
    """Respuesta de la validación previa de colisiones y enlace curricular (RF04, RF30)."""
    file_hash: str = Field(..., description="Hash SHA-256 inmutable del archivo subido")
    fecha_min: Optional[str] = Field(None, description="Fecha mínima detectada en los registros (AAAA-MM-DD HH:MM:SS)")
    fecha_max: Optional[str] = Field(None, description="Fecha máxima detectada en los registros (AAAA-MM-DD HH:MM:SS)")
    total_filas: int = Field(..., description="Total de filas procesables del archivo")
    existe_colision: bool = Field(..., description="Indica si existen registros previos en el rango de fechas para el recinto")
    registros_existentes: int = Field(0, description="Cantidad de registros existentes en la BD en ese intervalo")
    clave_enlace_detectada: Literal["rut", "matricula", "crosswalk", "ninguna"] = Field(
        ..., description="Clave de enlace curricular recomendada detectada automáticamente"
    )
    porcentaje_coincidencia_carreras: float = Field(
        0.0, description="Porcentaje estimado de registros que poseen carrera catalogada válida"
    )
    detalles_colision: Optional[str] = Field(None, description="Mensaje explicativo ante posible colisión o duplicado")
    hash_ya_procesado: bool = Field(False, description="Indica si el hash exacto del archivo ya fue ingresado previamente")
    trabajo_previo: Optional[Dict[str, Any]] = Field(None, description="Datos del trabajo previo si el hash ya existía")


class IngestionProcessRequest(BaseModel):
    """Parámetros de ejecución atómica del pipeline de ingesta (RF04, RF30)."""
    modo_solapamiento: Literal["merge", "overwrite"] = Field(
        "merge", description="merge: conserva registros previos e inserta nuevos; overwrite: reemplazo atómico del rango"
    )
    clave_enlace: Literal["rut", "matricula", "crosswalk"] = Field(
        "rut", description="Clave para cruce de dimensión académica del estudiante"
    )
    modo_enlace: Literal["tolerante", "mandatorio"] = Field(
        "tolerante", description="tolerante: registros huérfanos se insertan con 'Sin carrera catalogada'; mandatorio: aborta si no es 100%"
    )
    espacio_id: int = Field(1, description="ID del espacio institucional")
    tipo: str = Field("asistencia", description="Tipo de dataset: asistencia, vehicular, etc.")


class IngestionProcessResponse(BaseModel):
    """Resultado del procesamiento atómico de ingesta."""
    job_id: str
    status: str
    modo_solapamiento: str
    clave_enlace: str
    modo_enlace: str
    registros_procesados: int
    registros_insertados: int
    registros_eliminados: int
    carreras_catalogadas: int
    carreras_no_catalogadas: int
    file_hash: str
    detalle: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    estado: str
    registros_ok: int
    registros_error: int
    error_detail: Optional[str] = None


class IngestionHistoryItem(BaseModel):
    job_id: str
    filename: str
    tipo: str
    estado: str
    registros_ok: int
    registros_error: int
    creado_en: Optional[datetime] = None
    completado_en: Optional[datetime] = None
    file_hash: Optional[str] = None
    modo_solapamiento: Optional[str] = None
    clave_enlace: Optional[str] = None
    modo_enlace: Optional[str] = None
    espacio_id: Optional[int] = None
    error_detail: Optional[str] = None

    class Config:
        from_attributes = True
