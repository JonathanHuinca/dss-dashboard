from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


class SerieGrafico(BaseModel):
    nombre: str
    valores: List[Optional[float]]
    color: Optional[str] = None
    tipo_serie: Optional[str] = None  # line, column, area
    dash_type: Optional[str] = None  # solid, dash, dot


class GraficoNativoPayload(BaseModel):
    id: str
    titulo: str
    categoria: Optional[str] = "General"
    tipo_grafico: str = "column"  # line, column, bar, area, pie, doughnut
    eje_x_nombre: Optional[str] = ""
    eje_y_nombre: Optional[str] = ""
    categorias_x: List[Union[str, int, float]]
    series: List[SerieGrafico]
    subtitulo: Optional[str] = None


class SolicitudExportacionExcel(BaseModel):
    modulo_nombre: str = "Biblioteca Campus San Francisco"
    periodo_label: str = "Período Completo"
    filtros: Optional[Dict[str, str]] = None
    graficos: List[GraficoNativoPayload]
