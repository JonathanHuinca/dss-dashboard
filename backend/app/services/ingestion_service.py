"""
ingestion_service.py — Servicio de Ingesta Inteligente, ETL y Schema Matching (RF01-RF08).
"""
import asyncio
import gc
import io
import logging
import tempfile
import traceback
import unicodedata
import uuid
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import hashlib
from decimal import Decimal
import pandas as pd
from fastapi import HTTPException
from sqlalchemy import select, func, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import AttendanceEventDTO, VehicleEventDTO
from app.adapters.file_adapter import FileIngestionAdapter
from app.core.database import AsyncSessionLocal
from app.core.security import pseudonymize_person, encrypt_vehicle_patente
from app.core.security_cipher import encrypt_api_key
from app.domain.models import (
    IngestionJob,
    EventoAsistencia,
    EventoVehicular,
    DimEstudianteCarrera,
    DimCarreraPrograma,
)
from app.domain.modelos_institucionales_uct import (
    InstitucionalCampus,
    InstitucionalEdificios,
    InstitucionalTipoInmueble,
    InstitucionalAmbiente,
    InstitucionalTipoCarrera,
    InstitucionalCarreraPrograma,
    InstitucionalCarreraCampus,
    InstitucionalSituacionAlumno,
    InstitucionalViasIngreso,
    InstitucionalEstudiante,
    InstitucionalEstudianteCarrera,
)
from app.schemas.ingestion_schemas import (
    FileInspectionResponse,
    IngestionValidationResponse,
    IngestionProcessResponse,
    SchemaFieldMapping,
)
from app.services.attendance_service import AttendanceService
from app.services.vehicle_service import VehicleService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Matriz de Esquemas Objetivo y Sinonimia (RF03)
# ---------------------------------------------------------------------------
TARGET_SCHEMAS: Dict[str, List[Dict[str, Any]]] = {
    "asistencia": [
        {
            "target": "Fecha",
            "required": True,
            "description": "Fecha del evento de acceso (AAAA-MM-DD)",
            "classification": "analitico",
            "synonyms": ["fecha", "date", "dia", "fechahora", "timestamp"],
        },
        {
            "target": "Primera entrada",
            "required": True,
            "description": "Hora de ingreso inicial o marca temporal",
            "classification": "analitico",
            "synonyms": [
                "primera entrada",
                "hora",
                "hora entrada",
                "hora_entrada",
                "entrada",
                "primer ingreso",
                "first in",
                "in time",
                "ingreso",
                "time",
                "fechahora",
                "timestamp",
            ],
        },
        {
            "target": "Ultima salida",
            "required": False,
            "description": "Hora de egreso final",
            "classification": "analitico",
            "synonyms": [
                "ultima salida",
                "última salida",
                "hora salida",
                "hora_salida",
                "salida",
                "ultimo egreso",
                "last out",
                "out time",
                "egreso",
            ],
        },
        {
            "target": "Puerta de entrada",
            "required": False,
            "description": "Torniquete o acceso de entrada",
            "classification": "analitico",
            "synonyms": [
                "puerta",
                "door de entrada",
                "door entrada",
                "door_entrada",
                "puerta de entrada",
                "puerta entrada",
                "torniquete entrada",
                "acceso entrada",
                "torniquete",
            ],
        },
        {
            "target": "Puerta de salida",
            "required": False,
            "description": "Torniquete o acceso de salida",
            "classification": "analitico",
            "synonyms": [
                "door de salida",
                "door salida",
                "door_salida",
                "puerta de salida",
                "puerta salida",
                "torniquete salida",
                "acceso salida",
            ],
        },
        {
            "target": "Numero de matricula",
            "required": False,
            "description": "Identificador institucional o de visitante a seudonimizar con HMAC-SHA256",
            "classification": "seudonimizar",
            "synonyms": [
                "numero de matricula",
                "número de matrícula",
                "matricula",
                "matrícula",
                "personid",
                "person_id",
                "id_persona",
                "id_estudiante",
                "identificador",
                "rut",
                "run",
                "id visitante (seudónimo)",
                "id visitante",
                "visitante",
            ],
        },
        {
            "target": "Sentido",
            "required": False,
            "description": "Flujo de paso del torniquete (Entrada / Salida)",
            "classification": "analitico",
            "synonyms": ["sentido", "direccion", "dirección", "flujo", "movimiento", "tipo paso"],
        },
        {
            "target": "Edificio",
            "required": False,
            "description": "Edificio físico donde se ubica el torniquete",
            "classification": "analitico",
            "synonyms": ["edificio", "building", "recinto", "sector"],
        },
        {
            "target": "Estamento",
            "required": False,
            "description": "Categoría o estamento institucional del visitante",
            "classification": "analitico",
            "synonyms": ["estamento", "detalle estamento", "tipo usuario", "rol"],
        },
        {
            "target": "Persona",
            "required": False,
            "description": "Nombre de la persona — Purgado irreversible obligatorio (Ley 21.719)",
            "classification": "purgar",
            "synonyms": [
                "persona",
                "nombre",
                "nombres",
                "apellidos",
                "nombre completo",
                "estudiante",
                "usuario",
            ],
        },
        {
            "target": "Marcajes",
            "required": False,
            "description": "Conteo total de marcajes diarios",
            "classification": "analitico",
            "synonyms": ["marcajes", "total marcajes", "eventos", "accesos", "conteo"],
        },
        {
            "target": "Dif. salida (min)",
            "required": False,
            "description": "Minutos de permanencia calculada",
            "classification": "analitico",
            "synonyms": [
                "dif. salida (min)",
                "dif salida",
                "permanencia",
                "minutos",
                "duracion",
                "duración",
                "tiempo_estadia",
            ],
        },
    ],
    "marcajes_torniquete": [
        {
            "target": "Fecha",
            "required": True,
            "description": "Fecha del evento de acceso (AAAA-MM-DD)",
            "classification": "analitico",
            "synonyms": ["fecha", "date", "dia", "fechahora", "timestamp"],
        },
        {
            "target": "Hora",
            "required": True,
            "description": "Hora de marcaje en el torniquete (HH:MM o HH:MM:SS)",
            "classification": "analitico",
            "synonyms": [
                "hora",
                "time",
                "hora_marcaje",
                "horamarcaje",
                "timestamp",
                "primera entrada",
                "hora entrada",
            ],
        },
        {
            "target": "Puerta",
            "required": True,
            "description": "Punto de control de acceso o torniquete físico",
            "classification": "analitico",
            "synonyms": [
                "puerta",
                "door",
                "torniquete",
                "punto de control",
                "puerta de entrada",
                "puerta entrada",
                "acceso",
                "door de entrada",
            ],
        },
        {
            "target": "Sentido",
            "required": True,
            "description": "Sentido del tránsito (Entrada / Salida)",
            "classification": "analitico",
            "synonyms": ["sentido", "direccion", "dirección", "flujo", "movimiento", "tipo paso", "direction"],
        },
        {
            "target": "Edificio",
            "required": False,
            "description": "Identificador del edificio físico (ej. CSF02, CSF04)",
            "classification": "analitico",
            "synonyms": ["edificio", "building", "recinto", "sector", "sala"],
        },
        {
            "target": "Día semana",
            "required": False,
            "description": "Día de la semana del evento",
            "classification": "analitico",
            "synonyms": ["dia semana", "día semana", "dia_semana", "day of week", "dia"],
        },
        {
            "target": "Semana ISO",
            "required": False,
            "description": "Número de semana ISO del año",
            "classification": "analitico",
            "synonyms": ["semana iso", "semana", "week", "semana_iso", "iso week"],
        },
        {
            "target": "Mes",
            "required": False,
            "description": "Mes analítico (AAAA-MM)",
            "classification": "analitico",
            "synonyms": ["mes", "month", "periodo", "período"],
        },
        {
            "target": "Estamento",
            "required": False,
            "description": "Categoría o estamento institucional del visitante",
            "classification": "analitico",
            "synonyms": ["estamento", "tipo usuario", "rol", "categoria_usuario"],
        },
        {
            "target": "Detalle estamento",
            "required": False,
            "description": "Detalle complementario de la condición de paso o estamento",
            "classification": "analitico",
            "synonyms": ["detalle estamento", "detalle", "observacion", "observaciones", "motivo"],
        },
        {
            "target": "ID visitante (seudónimo)",
            "required": False,
            "description": "Identificador de visitante seudonimizado o a seudonimizar",
            "classification": "seudonimizar",
            "synonyms": [
                "id visitante (seudónimo)",
                "id visitante (seudonimo)",
                "id visitante",
                "visitante",
                "personid",
                "person_id",
                "id_persona",
                "identificador",
            ],
        },
        {
            "target": "Matrícula o RUT",
            "required": False,
            "description": "Registro de matrícula universitaria o RUT nacional para enlace curricular (RF30)",
            "classification": "seudonimizar",
            "synonyms": [
                "matricula",
                "matrícula",
                "matricula o rut",
                "matrícula o rut",
                "rut",
                "run",
                "cedula",
                "cédula",
                "numero de matricula",
                "número de matrícula",
                "estu_registro",
                "id_estudiante",
            ],
        },
    ],
    "vehicular": [
        {
            "target": "Fecha y Hora",
            "required": True,
            "description": "Marca temporal del tránsito ANPR",
            "classification": "analitico",
            "synonyms": [
                "fecha y hora",
                "hora",
                "fecha",
                "hora de paso",
                "tiempo",
                "timestamp",
                "datetime",
            ],
        },
        {
            "target": "Placa",
            "required": True,
            "description": "Patente del vehículo a seudonimizar y custodiar cifrada",
            "classification": "seudonimizar",
            "synonyms": [
                "placa",
                "patente",
                "numero de matricula",
                "número de matrícula",
                "matricula",
                "license plate",
                "plate",
            ],
        },
        {
            "target": "Camara",
            "required": True,
            "description": "Dispositivo LPR o punto de control vehicular",
            "classification": "analitico",
            "synonyms": [
                "camara",
                "cámara",
                "dispositivo",
                "device",
                "punto de control",
                "lpr",
                "gate",
            ],
        },
        {
            "target": "Sentido",
            "required": True,
            "description": "Flujo de movimiento (Entrada / Salida)",
            "classification": "analitico",
            "synonyms": ["sentido", "direccion", "dirección", "flujo", "direction", "movimiento", "direccion de conduccion", "dirección de conducción"],
        },
        {
            "target": "Tipo",
            "required": False,
            "description": "Categoría o tipología del vehículo",
            "classification": "analitico",
            "synonyms": [
                "tipo",
                "tipo de vehiculo",
                "tipo de vehículo",
                "vehicle type",
                "categoria",
                "categoría",
            ],
        },
        {
            "target": "Marca",
            "required": False,
            "description": "Marca fabricante del vehículo",
            "classification": "analitico",
            "synonyms": ["marca", "brand", "make"],
        },
        {
            "target": "Color",
            "required": False,
            "description": "Color exterior del vehículo",
            "classification": "analitico",
            "synonyms": ["color", "colour", "color del vehiculo", "color del vehículo"],
        },
    ],
    "curricular": [
        {
            "target": "RUT",
            "required": False,
            "description": "Identificador nacional para cruce curricular seguro",
            "classification": "seudonimizar",
            "synonyms": ["rut", "run", "cedula", "identificacion", "id", "usuario"],
        },
        {
            "target": "Matricula",
            "required": False,
            "description": "Registro de matrícula universitaria (10 dígitos)",
            "classification": "seudonimizar",
            "synonyms": ["matricula", "matrícula", "estu_registro", "id_estudiante", "student_id"],
        },
        {
            "target": "Carrera",
            "required": True,
            "description": "Nombre o código de la carrera universitaria",
            "classification": "analitico",
            "synonyms": ["carrera", "carr_nombre", "carr_codigo", "programa", "plan_estudios"],
        },
        {
            "target": "Facultad",
            "required": False,
            "description": "Facultad o unidad académica",
            "classification": "analitico",
            "synonyms": ["facultad", "fac_nombre", "unidad_academica"],
        },
        {
            "target": "Anio_Ingreso",
            "required": False,
            "description": "Año o cohorte de ingreso del estudiante",
            "classification": "analitico",
            "synonyms": [
                "anio_ingreso",
                "año_ingreso",
                "anho_ingreso",
                "cohorte",
                "promocion",
                "año",
                "anio",
            ],
        },
    ],
    "institucional_uct": [
        {
            "target": "estu_registro",
            "required": True,
            "description": "Matrícula institucional única del estudiante",
            "classification": "seudonimizar",
            "synonyms": ["estu_registro", "matricula", "registro", "id_estudiante"],
        },
        {
            "target": "estd_rut",
            "required": True,
            "description": "RUT del estudiante (Ley N° 21.719)",
            "classification": "seudonimizar",
            "synonyms": ["estd_rut", "rut", "run", "cedula"],
        },
        {
            "target": "carr_codigo",
            "required": True,
            "description": "Código de la carrera institucional",
            "classification": "analitico",
            "synonyms": ["carr_codigo", "carrera", "codigo_carrera"],
        },
        {
            "target": "salu_codigo",
            "required": True,
            "description": "Código de situación académica (SCD-2)",
            "classification": "analitico",
            "synonyms": ["salu_codigo", "situacion", "estado_alumno"],
        },
    ],
    "academico": [
        {
            "target": "Fecha",
            "required": True,
            "description": "Fecha del hito del calendario académico",
            "classification": "analitico",
            "synonyms": ["fecha", "date", "dia"],
        },
        {
            "target": "Hito",
            "required": True,
            "description": "Título o denominación de la actividad institucional",
            "classification": "analitico",
            "synonyms": ["hito", "evento", "nombre", "titulo", "título", "actividad"],
        },
        {
            "target": "Tipo",
            "required": False,
            "description": "Clasificación (feriado, examen, receso, suspensión)",
            "classification": "analitico",
            "synonyms": ["tipo", "categoria", "categoría", "clasificacion", "clasificación"],
        },
        {
            "target": "Descripcion",
            "required": False,
            "description": "Descripción detallada del hito",
            "classification": "analitico",
            "synonyms": ["descripcion", "descripción", "detalle", "observacion", "observaciones"],
        },
    ],
}


def _normalize_str(val: str) -> str:
    """Elimina tildes, signos y normaliza a minúsculas para matching léxico."""
    if not val:
        return ""
    n = unicodedata.normalize("NFKD", str(val))
    s = "".join(c for c in n if not unicodedata.combining(c))
    return "".join(c.lower() for c in s if c.isalnum() or c.isspace()).strip()


def _parse_fast_dt(date_val: Any, time_val: Any = None) -> Optional[datetime]:
    """Parseo de alto rendimiento para marcas temporales ISO y variantes."""
    if not date_val:
        return None
    d_str = str(date_val).strip()
    if d_str.lower() in ("nan", "none", "", "nat"):
        return None
    t_str = str(time_val).strip() if time_val else ""
    if t_str.lower() in ("nan", "none", "", "nat"):
        t_str = ""

    comb = f"{d_str} {t_str}".strip() if t_str else d_str
    if len(comb) >= 16 and comb[4] == "-" and comb[7] == "-":
        try:
            y = int(comb[:4])
            m = int(comb[5:7])
            d = int(comb[8:10])
            h = int(comb[11:13])
            mn = int(comb[14:16])
            s = int(comb[17:19]) if len(comb) >= 19 and comb[16] == ":" else 0
            return datetime(y, m, d, h, mn, s)
        except Exception:
            pass
    try:
        dt = pd.to_datetime(comb)
        if pd.notna(dt):
            return dt.to_pydatetime().replace(tzinfo=None)
    except Exception:
        pass
    return None


def _get_target_keywords_set(tipo: str) -> Set[str]:
    """Obtiene el conjunto de palabras clave esperadas para el tipo de archivo."""
    keywords = set()
    for field in TARGET_SCHEMAS.get(tipo, []):
        keywords.add(_normalize_str(field["target"]))
        for syn in field.get("synonyms", []):
            keywords.add(_normalize_str(syn))
    return keywords


def _estimate_excel_rows_fast(file_bytes: bytes, sheet_names: List[str], header_row: int = 0) -> int:
    """Calcula el número de filas en milisegundos usando openpyxl en modo read_only."""
    try:
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, keep_links=False)
        total = 0
        for s in sheet_names:
            if s in wb.sheetnames:
                ws = wb[s]
                if ws.max_row and ws.max_row > header_row:
                    total += (ws.max_row - header_row)
        wb.close()
        return total
    except Exception as e:
        logger.warning(f"No fue posible estimar filas con openpyxl: {e}")
        return 0


def _detect_header_row_csv(
    file_bytes: bytes,
    target_keywords: Set[str],
    max_rows: Optional[int] = None,
) -> Tuple[int, pd.DataFrame, int]:
    """Detecta automáticamente la cabecera real en CSV evaluando las primeras 15 filas."""
    encodings = ["utf-8-sig", "utf-8", "latin-1", "iso-8859-1"]
    lines: List[str] = []
    chosen_encoding = "utf-8-sig"

    for enc in encodings:
        try:
            sample_text = file_bytes[:65536].decode(enc)
            lines = sample_text.splitlines()[:20]
            chosen_encoding = enc
            break
        except UnicodeDecodeError:
            continue

    best_row = 0
    max_matches = -1

    for i, line in enumerate(lines[:15]):
        line_norm = _normalize_str(line)
        matches = sum(1 for kw in target_keywords if kw and kw in line_norm)
        if matches > max_matches and matches >= 2:
            max_matches = matches
            best_row = i

    df = pd.read_csv(
        io.BytesIO(file_bytes),
        skiprows=best_row,
        nrows=max_rows,
        encoding=chosen_encoding,
        dtype=str,
        keep_default_na=False,
    )

    if max_rows is not None:
        try:
            total_lines = file_bytes.count(b"\n")
            total_rows = max(0, total_lines - best_row)
        except Exception:
            total_rows = len(df)
    else:
        total_rows = len(df)

    return best_row, df, total_rows


def _detect_header_row_excel(
    file_bytes: bytes,
    target_keywords: Set[str],
    max_rows: Optional[int] = None,
) -> Tuple[int, pd.DataFrame, int]:
    """
    Detecta la cabecera real en Excel (XLSX/XLS), admitiendo múltiples hojas de datos
    (ej. CSF02 y CSF04) y descartando hojas no procesables (ej. Notas, Presentación, TD).
    Retorna (header_row_index, df, total_rows_estimated).
    """
    xl = pd.ExcelFile(io.BytesIO(file_bytes))
    sheet_names = xl.sheet_names

    excluded_names = {
        "notas", "nota", "metadata", "instrucciones", "readme",
        "presentacion", "presentación", "td", "salas"
    }

    # Prioridad: si existe una hoja maestra consolidada, usarla de forma exclusiva
    consolidated_candidates = [
        s for s in sheet_names
        if any(k in _normalize_str(s) for k in ["maestro consolidado", "maestro curricular", "maestro estudiantes", "estudiantes consolidado", "consolidado"])
    ]

    candidate_sheets = []
    if consolidated_candidates:
        candidate_sheets = [consolidated_candidates[0]]
    elif len(sheet_names) > 1:
        for s in sheet_names:
            if _normalize_str(s) not in excluded_names:
                candidate_sheets.append(s)
    if not candidate_sheets:
        candidate_sheets = sheet_names

    valid_dfs = []
    chosen_header_row = 0

    for s in candidate_sheets:
        try:
            df_raw = xl.parse(s, header=None, nrows=20, dtype=str, keep_default_na=False)
            best_row = 0
            max_matches = -1

            for i, row in df_raw.iterrows():
                row_text = " ".join([_normalize_str(str(v)) for v in row if pd.notna(v) and str(v).strip()])
                matches = sum(1 for kw in target_keywords if kw and kw in row_text)
                if matches > max_matches and matches >= 2:
                    max_matches = matches
                    best_row = int(i)

            # Convención vehicular HikCentral (skiprows=6)
            if max_matches < 2 and len(df_raw) > 6:
                for i, row in df_raw.iloc[5:8].iterrows():
                    row_text = " ".join([_normalize_str(str(v)) for v in row if pd.notna(v) and str(v).strip()])
                    if any(k in row_text for k in ["matricula", "placa", "camara", "hora"]):
                        best_row = int(i)
                        max_matches = 2
                        break

            if max_matches >= 2 or len(candidate_sheets) == 1:
                df_sheet = xl.parse(s, skiprows=best_row, nrows=max_rows, dtype=str, keep_default_na=False)
                col_names_low = [str(c).strip().lower() for c in df_sheet.columns]
                if "edificio" not in col_names_low:
                    if "csf02" in s.lower():
                        df_sheet["Edificio"] = "CSF02"
                    elif "csf04" in s.lower():
                        df_sheet["Edificio"] = "CSF04"
                valid_dfs.append(df_sheet)
                chosen_header_row = best_row
        except Exception as e:
            logger.warning(f"No fue posible analizar hoja {s}: {e}")

    # Estimar total de filas en tiempo constante
    if max_rows is not None:
        total_estimated_rows = _estimate_excel_rows_fast(file_bytes, candidate_sheets, chosen_header_row)
        if total_estimated_rows <= 0:
            total_estimated_rows = sum(len(d) for d in valid_dfs)
    else:
        total_estimated_rows = sum(len(d) for d in valid_dfs)

    if not valid_dfs:
        df_sheet = xl.parse(sheet_names[0], nrows=max_rows, dtype=str, keep_default_na=False)
        return 0, df_sheet, len(df_sheet)

    combined_df = pd.concat(valid_dfs, ignore_index=True)
    return chosen_header_row, combined_df, total_estimated_rows


def _sanitize_preview_value(col_name: str, val: Any, tipo: str = "") -> Any:
    """Sanitiza campos sensibles conforme a la Ley N° 21.719 en la previsualización."""
    if val is None or pd.isna(val):
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() in ("nan", "none", "null"):
        return None

    col_norm = _normalize_str(col_name)

    # 1. PII directa: Purgado irreversible
    if any(
        k in col_norm
        for k in [
            "nombre",
            "persona",
            "correo",
            "email",
            "telefono",
            "celular",
            "fono",
            "direccion",
            "apellidos",
        ]
    ):
        return "[DATO PURGADO - LEY 21.719]"

    # 2. Patentes vehiculares (prioridad si el contexto es vehicular o contiene placa/patente)
    if tipo == "vehicular" or any(k in col_norm for k in ["placa", "patente"]):
        if any(k in col_norm for k in ["placa", "patente", "matricula"]):
            if len(val_str) >= 4:
                return f"VEH-***{val_str[-2:]}"
            return "[SEUDONIMIZADO]"

    # 3. Identificadores institucionales: Enmascaramiento parcial
    if any(
        k in col_norm
        for k in ["rut", "run", "cedula", "matricula", "personid", "estu_registro", "visitante", "id visitante"]
    ):
        if len(val_str) > 4:
            return f"EST-***{val_str[-4:]}"
        return "[SEUDONIMIZADO]"

    return val_str


def es_archivo_institucional_uct(file_source: Any) -> bool:
    """Detecta si el archivo es un Excel multitabla con el esquema institucional UCT."""
    import openpyxl
    try:
        if isinstance(file_source, (str, Path)):
            wb = openpyxl.load_workbook(file_source, read_only=True, keep_links=False)
        elif isinstance(file_source, bytes):
            wb = openpyxl.load_workbook(io.BytesIO(file_source), read_only=True, keep_links=False)
        else:
            return False
        sheets = {_normalize_str(s) for s in wb.sheetnames}
        wb.close()
        return ("estudiante_carrera" in sheets or "estudiante" in sheets) and ("campus" in sheets or "carrera_programa" in sheets)
    except Exception:
        return False


async def inspect_uploaded_file(
    file_bytes: bytes,
    filename: str,
    tipo: str,
    espacio_id: int = 1,
) -> FileInspectionResponse:
    """
    Inspecciona en memoria volátil un archivo CSV o Excel sin guardarlo en disco.
    Aplica Schema Matching con semáforo y sanitización de datos (RF03, Ley 21.719).
    """
    tipo_clean = tipo.strip().lower()
    fn_lower = filename.lower()
    is_csv = fn_lower.endswith(".csv")
    is_excel = fn_lower.endswith(".xlsx") or fn_lower.endswith(".xls")

    if not (is_csv or is_excel):
        raise HTTPException(
            status_code=400,
            detail="Formato de archivo no compatible. Solo se admiten archivos .csv o .xlsx/.xls",
        )

    # Autodetección de esquema institucional UCT (11 tablas)
    if is_excel and es_archivo_institucional_uct(file_bytes):
        tipo_clean = "institucional_uct"
        import openpyxl
        try:
            wb_prev = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            if "ESTUDIANTE_CARRERA" in wb_prev.sheetnames:
                ws_ec = wb_prev["ESTUDIANTE_CARRERA"]
                rows_ec = list(ws_ec.iter_rows(values_only=True))
                if len(rows_ec) > 2:
                    header_row_index = 2
                    detected_cols = [str(c).strip() for c in rows_ec[2] if c is not None and str(c).strip()]
                    sample_data = []
                    for r in rows_ec[3:8]:
                        if any(c is not None for c in r):
                            sample_data.append({detected_cols[i]: (str(r[i]) if i < len(r) and r[i] is not None else "") for i in range(min(len(detected_cols), len(r)))})
                    df = pd.DataFrame(sample_data)
                    total_rows = len(rows_ec) - 3
            wb_prev.close()
        except Exception as e_inst:
            logger.warning(f"Error cargando muestra institucional UCT: {e_inst}")
            header_row_index, df, total_rows = 0, pd.DataFrame(), 0
    else:
        target_keywords = _get_target_keywords_set(tipo_clean)
        try:
            if is_csv:
                header_row_index, df, total_rows = await asyncio.to_thread(
                    _detect_header_row_csv, file_bytes, target_keywords, 25
                )
            else:
                header_row_index, df, total_rows = await asyncio.to_thread(
                    _detect_header_row_excel, file_bytes, target_keywords, 25
                )
        except Exception as e:
            logger.error(f"Error procesando estructura del archivo {filename}: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"No fue posible leer la estructura del archivo. Detalle: {str(e)}",
            )
        detected_cols = [str(c).strip() for c in df.columns if str(c).strip() and not str(c).startswith("Unnamed:")]

    # Autodetección inteligente de formato para accesos peatonales de biblioteca
    norm_detected = [_normalize_str(c) for c in detected_cols]
    if tipo_clean in ("asistencia", "marcajes_torniquete"):
        has_hora = any(c == "hora" or "hora_marcaje" in c for c in norm_detected)
        has_puerta = any("puerta" in c for c in norm_detected)
        has_sentido = any("sentido" in c for c in norm_detected)
        has_primera_entrada = any("primera entrada" in c for c in norm_detected)
        if (has_hora and (has_puerta or has_sentido)) and not has_primera_entrada:
            tipo_clean = "marcajes_torniquete"
        elif has_primera_entrada:
            tipo_clean = "asistencia"

    schema_mappings: List[SchemaFieldMapping] = []
    used_cols: Set[str] = set()

    # Si es dataset personalizado (custom CSV)
    if tipo_clean == "custom":
        for col in detected_cols:
            col_norm = _normalize_str(col)
            if any(k in col_norm for k in ["nombre", "correo", "email", "telefono"]):
                classification = "purgar"
            elif any(k in col_norm for k in ["rut", "matricula", "patente", "id"]):
                classification = "seudonimizar"
            else:
                classification = "analitico"

            schema_mappings.append(
                SchemaFieldMapping(
                    target_field=col,
                    matched_column=col,
                    status="verde",
                    required=False,
                    description="Columna de dataset personalizado",
                    classification=classification,
                )
            )
        all_required_matched = True
        missing_required_fields: List[str] = []

    else:
        # Schema matching para tipos estándar
        expected_fields = TARGET_SCHEMAS.get(tipo_clean, [])
        norm_to_actual_cols = {_normalize_str(c): c for c in detected_cols}

        missing_required_fields = []

        for expected in expected_fields:
            target_name = expected["target"]
            target_norm = _normalize_str(target_name)
            synonyms_norm = [_normalize_str(s) for s in expected.get("synonyms", [])]
            is_req = expected["required"]
            desc = expected.get("description", "")
            classification = expected.get("classification", "analitico")

            matched_col: Optional[str] = None
            status = "rojo"

            # 1. Coincidencia exacta con el nombre objetivo
            for norm_c, actual_c in norm_to_actual_cols.items():
                if actual_c not in used_cols and norm_c == target_norm:
                    matched_col = actual_c
                    status = "verde"
                    used_cols.add(actual_c)
                    break

            # 2. Coincidencia por sinónimo
            if not matched_col:
                for norm_c, actual_c in norm_to_actual_cols.items():
                    if actual_c not in used_cols and norm_c in synonyms_norm:
                        matched_col = actual_c
                        status = "amarillo"
                        used_cols.add(actual_c)
                        break

            # 3. Coincidencia por inclusión (el término sinónimo está presente en la columna detectada)
            if not matched_col:
                for norm_c, actual_c in norm_to_actual_cols.items():
                    if actual_c not in used_cols:
                        if any(syn in norm_c for syn in synonyms_norm if len(syn) >= 4):
                            matched_col = actual_c
                            status = "amarillo"
                            used_cols.add(actual_c)
                            break

            if is_req and not matched_col:
                missing_required_fields.append(target_name)

            schema_mappings.append(
                SchemaFieldMapping(
                    target_field=target_name,
                    matched_column=matched_col,
                    status=status,
                    required=is_req,
                    description=desc,
                    classification=classification,
                )
            )

        all_required_matched = len(missing_required_fields) == 0

    # Construir preview de las primeras 5 filas con estricta sanitización
    preview_df = df.head(5).copy()
    preview_rows: List[Dict[str, Any]] = []

    for _, row in preview_df.iterrows():
        clean_row = {}
        for col in detected_cols:
            raw_val = row.get(col)
            clean_row[col] = _sanitize_preview_value(col, raw_val, tipo_clean)
        preview_rows.append(clean_row)

    return FileInspectionResponse(
        filename=filename,
        tipo=tipo_clean,
        espacio_id=espacio_id,
        header_row_index=header_row_index,
        total_rows_estimated=total_rows,
        columns_detected=detected_cols,
        schema_mapping=schema_mappings,
        preview_rows=preview_rows,
        all_required_matched=all_required_matched,
        missing_required_fields=missing_required_fields,
    )


# ---------------------------------------------------------------------------
# Utilidades de Hash y Detección de Rango Temporal (RF04, RF30)
# ---------------------------------------------------------------------------
def calcular_hash_archivo(file_bytes: bytes) -> str:
    """Calcula hash SHA-256 criptográfico de los bytes en memoria volátil."""
    return hashlib.sha256(file_bytes).hexdigest()


def detectar_clave_enlace(columnas: List[str]) -> str:
    """Determina la clave de enlace curricular óptima según columnas presentes."""
    norm_cols = [_normalize_str(c) for c in columnas]
    has_rut = any(any(k in c for k in ["rut", "run", "cedula"]) for c in norm_cols)
    has_mat = any(any(k in c for k in ["matricula", "estu_registro", "personid", "person_id"]) for c in norm_cols)
    if has_rut and has_mat:
        return "crosswalk"
    if has_rut:
        return "rut"
    if has_mat:
        return "matricula"
    return "ninguna"


def extraer_dataframe_archivo(file_bytes: bytes, filename: str, tipo: str, max_rows: Optional[int] = None) -> Tuple[int, pd.DataFrame]:
    """Carga DataFrame desde memoria detectando la fila de cabecera real."""
    tipo_clean = tipo.strip().lower()
    keywords = _get_target_keywords_set(tipo_clean)
    if filename.lower().endswith((".xlsx", ".xls")):
        header_idx, df, _ = _detect_header_row_excel(file_bytes, keywords, max_rows=max_rows)
        return header_idx, df
    header_idx, df, _ = _detect_header_row_csv(file_bytes, keywords, max_rows=max_rows)
    return header_idx, df


def extraer_rango_fechas(df: pd.DataFrame) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Extrae el rango temporal [fecha_min, fecha_max] normalizado a naive datetime."""
    if df.empty:
        return None, None

    date_col = None
    time_col = None
    for c in df.columns:
        c_norm = _normalize_str(c)
        if not date_col and any(k in c_norm for k in ["fecha", "date", "dia", "fechahora"]):
            date_col = c
        if not time_col and any(k in c_norm for k in ["primera entrada", "hora entrada", "hora", "timestamp", "time"]):
            time_col = c

    parsed_dates = []
    if date_col and time_col:
        for _, row in df.head(2000).iterrows():
            d_val = str(row.get(date_col, "")).strip()
            t_val = str(row.get(time_col, "")).strip()
            if d_val and t_val:
                try:
                    dt = pd.to_datetime(f"{d_val} {t_val}", errors="coerce")
                    if pd.notna(dt):
                        parsed_dates.append(dt.to_pydatetime().replace(tzinfo=None))
                except Exception:
                    pass

    if not parsed_dates and date_col:
        for val in df[date_col].dropna().unique()[:2000]:
            val_str = str(val).strip()
            if not val_str:
                continue
            try:
                dt = pd.to_datetime(val_str, errors="coerce")
                if pd.notna(dt):
                    parsed_dates.append(dt.to_pydatetime().replace(tzinfo=None))
            except Exception:
                continue

    if not parsed_dates and time_col:
        for val in df[time_col].dropna().unique()[:2000]:
            val_str = str(val).strip()
            if not val_str:
                continue
            try:
                dt = pd.to_datetime(val_str, errors="coerce")
                if pd.notna(dt):
                    parsed_dates.append(dt.to_pydatetime().replace(tzinfo=None))
            except Exception:
                continue

    if not parsed_dates:
        return None, None

    min_d = min(parsed_dates)
    max_d = max(parsed_dates)
    if max_d.hour == 0 and max_d.minute == 0 and max_d.second == 0:
        max_d = max_d.replace(hour=23, minute=59, second=59)

    return min_d, max_d


# ---------------------------------------------------------------------------
# Validación Previa de Colisiones y Enlace Curricular (RF04, RF30)
# ---------------------------------------------------------------------------
async def validar_archivo_ingesta(
    file_bytes: bytes,
    filename: str,
    tipo: str,
    espacio_id: int,
    db: AsyncSession,
) -> IngestionValidationResponse:
    """
    Realiza la verificación criptográfica SHA-256, chequeo de solapamiento de fechas
    y factibilidad de enlace curricular antes de persistir datos en la base.
    """
    file_hash = calcular_hash_archivo(file_bytes)
    tipo_clean = tipo.strip().lower()

    # 1. Chequeo de duplicados en ingestion_jobs por hash SHA-256
    stmt_job = (
        select(IngestionJob)
        .where(IngestionJob.file_hash == file_hash)
        .order_by(IngestionJob.creado_en.desc())
    )
    res_job = await db.execute(stmt_job)
    prev_job = res_job.scalars().first()

    hash_ya_procesado = prev_job is not None and prev_job.estado == "completed"
    trabajo_previo = None
    if prev_job:
        trabajo_previo = {
            "job_id": str(prev_job.job_id),
            "filename": prev_job.filename,
            "estado": prev_job.estado,
            "fecha": prev_job.creado_en.strftime("%Y-%m-%d %H:%M:%S") if prev_job.creado_en else None,
            "registros_ok": prev_job.registros_ok,
        }

    # 2. Cargar muestra ligera e identificar total de filas y rango de fechas (RF04)
    is_excel = filename.lower().endswith((".xlsx", ".xls"))
    header_idx, df = await asyncio.to_thread(extraer_dataframe_archivo, file_bytes, filename, tipo_clean, 1000)

    # Autodetección de subtipo para validar contra el modelo correcto
    norm_detected = [_normalize_str(c) for c in df.columns]
    if tipo_clean in ("asistencia", "marcajes_torniquete"):
        has_hora = any(c == "hora" or "hora_marcaje" in c for c in norm_detected)
        has_puerta = any("puerta" in c for c in norm_detected)
        has_sentido = any("sentido" in c for c in norm_detected)
        has_primera_entrada = any("primera entrada" in c for c in norm_detected)
        if (has_hora and (has_puerta or has_sentido)) and not has_primera_entrada:
            tipo_clean = "marcajes_torniquete"
        elif has_primera_entrada:
            tipo_clean = "asistencia"

    if is_excel:
        import openpyxl
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, keep_links=False)
            candidate_sheets = [s for s in wb.sheetnames if _normalize_str(s) not in {"notas", "nota", "metadata", "instrucciones", "readme", "presentacion", "presentación", "td", "salas"}]
            total_filas = _estimate_excel_rows_fast(file_bytes, candidate_sheets, header_idx)
            wb.close()
        except Exception:
            total_filas = len(df)
        if total_filas <= 0:
            total_filas = len(df)
    else:
        total_filas = max(file_bytes.count(b'\n') - header_idx - 1, len(df))

    min_dt, max_dt = extraer_rango_fechas(df)

    # Si el nombre del archivo contiene un rango explícito de fechas (ej. 2026-03-01_a_2026-10-14)
    import re
    date_matches = re.findall(r'(20\d{2}[-_/]\d{2}[-_/]\d{2})', filename)
    if len(date_matches) >= 2:
        try:
            fn_d1 = datetime.strptime(date_matches[0].replace("_", "-").replace("/", "-"), "%Y-%m-%d")
            fn_d2 = datetime.strptime(date_matches[1].replace("_", "-").replace("/", "-"), "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            if fn_d1 <= fn_d2:
                min_dt = min(min_dt, fn_d1) if min_dt else fn_d1
                max_dt = max(max_dt, fn_d2) if max_dt else fn_d2
        except Exception:
            pass

    fecha_min_str = min_dt.strftime("%Y-%m-%d %H:%M:%S") if min_dt else None
    fecha_max_str = max_dt.strftime("%Y-%m-%d %H:%M:%S") if max_dt else None

    # 3. Detección de colisiones en SQL Server para el recinto
    registros_existentes = 0
    if min_dt and max_dt and tipo_clean in ("asistencia", "marcajes_torniquete"):
        stmt_col = (
            select(func.count())
            .select_from(EventoAsistencia)
            .where(
                EventoAsistencia.espacio_id == espacio_id,
                EventoAsistencia.time >= min_dt,
                EventoAsistencia.time <= max_dt,
            )
        )
        res_col = await db.execute(stmt_col)
        registros_existentes = int(res_col.scalar() or 0)
    elif min_dt and max_dt and tipo_clean == "vehicular":
        stmt_col = (
            select(func.count())
            .select_from(EventoVehicular)
            .where(
                EventoVehicular.espacio_id == espacio_id,
                EventoVehicular.time >= min_dt,
                EventoVehicular.time <= max_dt,
            )
        )
        res_col = await db.execute(stmt_col)
        registros_existentes = int(res_col.scalar() or 0)

    existe_colision = registros_existentes > 0

    # 4. Detección de clave de cruce y porcentaje de coincidencia curricular
    clave_detectada = detectar_clave_enlace(list(df.columns))
    coincidencia_carreras = 0.0

    # Verificar si el archivo ya contiene columna carrera
    carrera_cols = [c for c in df.columns if any(k in _normalize_str(c) for k in ["carrera", "carr_nombre", "programa"])]
    if carrera_cols:
        con_carrera = df[carrera_cols[0]].dropna().replace("", None).count()
        coincidencia_carreras = round((con_carrera / total_filas) * 100, 1) if total_filas > 0 else 0.0
    else:
        # Verificar cuántos estudiantes ya existen en dim_estudiante_carrera
        try:
            stmt_est_cnt = select(func.count()).select_from(DimEstudianteCarrera)
            res_est_cnt = await db.execute(stmt_est_cnt)
            total_catalogados = res_est_cnt.scalar() or 0
            if total_catalogados > 0:
                coincidencia_carreras = 50.0  # Estimación basada en catálogo presente
        except Exception:
            pass

    # 5. Redacción de detalles informativos de colisión
    detalles = []
    if hash_ya_procesado:
        detalles.append(f"Archivo previamente procesado ({prev_job.filename} con {prev_job.registros_ok} registros).")
    if existe_colision:
        detalles.append(
            f"Se detectaron {registros_existentes} registros en base de datos para el período {fecha_min_str} a {fecha_max_str}. "
            f"Se recomienda seleccionar 'Fusión / Merge' para no duplicar o 'Sobrescritura Atómica' para reemplazar con versión enriquecida."
        )
    if not detalles:
        detalles.append("No se detectaron colisiones ni duplicados. Archivo listo para ingesta.")

    return IngestionValidationResponse(
        file_hash=file_hash,
        fecha_min=fecha_min_str,
        fecha_max=fecha_max_str,
        total_filas=total_filas,
        existe_colision=existe_colision,
        registros_existentes=registros_existentes,
        clave_enlace_detectada=clave_detectada if clave_detectada in ("rut", "matricula", "crosswalk") else "ninguna",
        porcentaje_coincidencia_carreras=coincidencia_carreras,
        detalles_colision=" | ".join(detalles),
        hash_ya_procesado=hash_ya_procesado,
        trabajo_previo=trabajo_previo,
    )


# ---------------------------------------------------------------------------
# Mapeo Asistido a DTOs con Enlace Curricular Flexible (RF30)
# ---------------------------------------------------------------------------
async def _mapear_df_a_dtos_asistencia(
    df: pd.DataFrame,
    espacio_id: int,
    clave_enlace: str,
    modo_enlace: str,
    db: AsyncSession,
) -> Tuple[List[AttendanceEventDTO], int, int]:
    """
    Convierte DataFrame en DTOs de asistencia aplicando enlace curricular flexible (RF30).
    Retorna (dtos, carreras_catalogadas, carreras_no_catalogadas).
    """
    col_map = {}
    for c in df.columns:
        c_norm = _normalize_str(c)
        if "fecha" not in col_map and any(k in c_norm for k in ["fecha", "date", "dia"]):
            col_map["fecha"] = c
        if "primera_entrada" not in col_map and any(k in c_norm for k in ["primera entrada", "hora entrada", "in time", "ingreso"]):
            col_map["primera_entrada"] = c
        if "ultima_salida" not in col_map and any(k in c_norm for k in ["ultima salida", "última salida", "hora salida", "out time", "egreso"]):
            col_map["ultima_salida"] = c
        if "hora_general" not in col_map and any(k in c_norm for k in ["hora", "timestamp", "time", "fechahora"]):
            col_map["hora_general"] = c
        if "id_visitante" not in col_map and any(k in c_norm for k in ["id visitante", "visitante"]):
            col_map["id_visitante"] = c
        if "identificador" not in col_map and any(k in c_norm for k in ["personid", "person_id", "id_persona", "identificador"]):
            col_map["identificador"] = c
        if "rut" not in col_map and any(k in c_norm for k in ["rut", "run", "cedula"]):
            col_map["rut"] = c
        if "matricula" not in col_map and any(k in c_norm for k in ["matricula", "estu_registro"]):
            col_map["matricula"] = c
        if "door_in" not in col_map and any(k in c_norm for k in ["door de entrada", "door entrada", "puerta de entrada", "puerta entrada", "torniquete entrada"]):
            col_map["door_in"] = c
        if "door_out" not in col_map and any(k in c_norm for k in ["door de salida", "door salida", "puerta de salida", "puerta salida", "torniquete salida"]):
            col_map["door_out"] = c
        if "puerta_gral" not in col_map and any(k in c_norm for k in ["puerta", "door", "torniquete", "punto de control"]):
            col_map["puerta_gral"] = c
        if "sentido" not in col_map and any(k in c_norm for k in ["sentido", "direccion", "dirección", "flujo", "movimiento"]):
            col_map["sentido"] = c
        if "edificio" not in col_map and any(k in c_norm for k in ["edificio", "building", "recinto"]):
            col_map["edificio"] = c
        if "carrera" not in col_map and any(k in c_norm for k in ["carrera", "programa", "plan_estudios", "carr_nombre"]):
            col_map["carrera"] = c
        if "facultad" not in col_map and "facultad" in c_norm:
            col_map["facultad"] = c
        if "estamento" not in col_map and any(k in c_norm for k in ["estamento", "tipo_usuario", "tipo usuario", "rol", "categoria"]):
            col_map["estamento"] = c

    # Cargar catálogo de estudiantes en memoria
    maestro_estudiantes = {}
    try:
        stmt_m = select(DimEstudianteCarrera)
        res_m = await db.execute(stmt_m)
        for est in res_m.scalars().all():
            if est.rut_hash:
                maestro_estudiantes[f"rut:{est.rut_hash}"] = est
            if est.matricula:
                maestro_estudiantes[f"mat:{str(est.matricula).strip().lower()}"] = est
            if est.person_id_hash:
                maestro_estudiantes[f"pid:{est.person_id_hash}"] = est
    except Exception as e:
        logger.warning(f"No se pudo consultar dim_estudiante_carrera: {e}")

    dtos: List[AttendanceEventDTO] = []
    carreras_catalogadas = 0
    carreras_no_catalogadas = 0
    huerfanos = []

    records = df.to_dict(orient="records")

    # 1. Pre-conteo de accesos diarios por persona/matrícula (RF03, DSS UCT)
    col_fecha_name = col_map.get("fecha", "")
    col_mat_name = col_map.get("matricula", "")
    col_rut_name = col_map.get("rut", "")
    col_id_name = col_map.get("id_visitante", "") or col_map.get("identificador", "")
    col_estamento_name = col_map.get("estamento", "")

    marcajes_por_persona_dia = {}
    for r in records:
        # En biblioteca (espacio_id == 1), filtrar estrictamente solo Estudiante
        if espacio_id == 1 and col_estamento_name:
            est_raw = str(r.get(col_estamento_name, "")).strip().lower()
            if est_raw != "estudiante":
                continue

        f_val = str(r.get(col_fecha_name, "")).strip()[:10]
        uid = ""
        if col_mat_name:
            v = str(r.get(col_mat_name, "")).strip()
            if v.lower() not in ("nan", "none", "", "null"):
                uid = v
        if not uid and col_rut_name:
            v = str(r.get(col_rut_name, "")).strip()
            if v.lower() not in ("nan", "none", "", "null"):
                uid = v
        if not uid and col_id_name:
            v = str(r.get(col_id_name, "")).strip()
            if v.lower() not in ("nan", "none", "", "null"):
                uid = v

        if f_val and uid:
            clave = (f_val, uid)
            marcajes_por_persona_dia[clave] = marcajes_por_persona_dia.get(clave, 0) + 1

    for idx, row in enumerate(records):
        # En biblioteca (espacio_id == 1), omitir filas que no correspondan a Estudiante
        if espacio_id == 1 and col_estamento_name:
            est_raw = str(row.get(col_estamento_name, "")).strip().lower()
            if est_raw != "estudiante":
                continue

        fecha_val = row.get(col_map.get("fecha", ""), "") if "fecha" in col_map else ""
        pe_val = row.get(col_map.get("primera_entrada", ""), "") if "primera_entrada" in col_map else ""
        us_val = row.get(col_map.get("ultima_salida", ""), "") if "ultima_salida" in col_map else ""
        hora_val = row.get(col_map.get("hora_general", ""), "") if "hora_general" in col_map else ""

        pe_dt = _parse_fast_dt(fecha_val, pe_val) if pe_val else None
        us_dt = _parse_fast_dt(fecha_val, us_val) if us_val else None

        event_time = pe_dt or us_dt or _parse_fast_dt(fecha_val, hora_val) or _parse_fast_dt(fecha_val)

        if not event_time:
            continue

        # Identificador y Hash Ley 21.719
        raw_id = ""
        if "matricula" in col_map:
            val_m = str(row.get(col_map["matricula"], "")).strip()
            if val_m.lower() not in ("nan", "none", "", "null"):
                raw_id = val_m
        if not raw_id and "rut" in col_map:
            val_r = str(row.get(col_map["rut"], "")).strip()
            if val_r.lower() not in ("nan", "none", "", "null"):
                raw_id = val_r
        if not raw_id and "id_visitante" in col_map:
            val_v = str(row.get(col_map["id_visitante"], "")).strip()
            if val_v.lower() not in ("nan", "none", "", "null"):
                raw_id = val_v
        if not raw_id and "identificador" in col_map:
            val_id = str(row.get(col_map["identificador"], "")).strip()
            if val_id.lower() not in ("nan", "none", "", "null"):
                raw_id = val_id

        # Puertas y Sentido de paso
        door_in = str(row.get(col_map.get("door_in", ""), "")).strip() if "door_in" in col_map else None
        door_out = str(row.get(col_map.get("door_out", ""), "")).strip() if "door_out" in col_map else None
        puerta_gral = str(row.get(col_map.get("puerta_gral", ""), "")).strip() if "puerta_gral" in col_map else None

        if door_in in ("", "nan", "None"):
            door_in = None
        if door_out in ("", "nan", "None"):
            door_out = None
        if puerta_gral in ("", "nan", "None"):
            puerta_gral = None

        puerta_nominal = puerta_gral or door_in or door_out

        if raw_id:
            person_hash = pseudonymize_person(raw_id)
        else:
            door_sample = puerta_nominal or "torniquete"
            person_hash = f"anon_{hashlib.sha256(f'{event_time}_{door_sample}_{idx}'.encode()).hexdigest()[:16]}"

        # Cruce curricular flexible (RF30)
        carrera_res = None
        facultad_res = None

        if "carrera" in col_map:
            c_val = str(row.get(col_map["carrera"], "")).strip()
            if c_val and c_val.lower() not in ("nan", "none", "", "null"):
                carrera_res = c_val
        if "facultad" in col_map:
            f_val = str(row.get(col_map["facultad"], "")).strip()
            if f_val and f_val.lower() not in ("nan", "none", "", "null"):
                facultad_res = f_val

        # Si aún no tiene carrera, consultar maestro en memoria
        if not carrera_res and maestro_estudiantes:
            matched_est = None
            if clave_enlace in ("rut", "crosswalk") and "rut" in col_map:
                r_val = str(row.get(col_map["rut"], "")).strip()
                if r_val and r_val.lower() not in ("nan", "none", ""):
                    r_hash = pseudonymize_person(r_val)
                    matched_est = maestro_estudiantes.get(f"rut:{r_hash}")

            if not matched_est and clave_enlace in ("matricula", "crosswalk") and "matricula" in col_map:
                m_val = str(row.get(col_map["matricula"], "")).strip().lower()
                if m_val and m_val not in ("nan", "none", ""):
                    matched_est = maestro_estudiantes.get(f"mat:{m_val}")

            if not matched_est and raw_id:
                matched_est = maestro_estudiantes.get(f"pid:{person_hash}")

            if matched_est:
                carrera_res = matched_est.carr_nombre
                facultad_res = matched_est.facultad

        if carrera_res and carrera_res != "Sin carrera catalogada":
            carreras_catalogadas += 1
        else:
            carreras_no_catalogadas += 1
            if modo_enlace == "mandatorio":
                huerfanos.append(f"Fila {idx+1}: ID '{raw_id[:6]}***'")
            else:
                carrera_res = "Sin carrera catalogada"
                facultad_res = facultad_res or "Sin facultad"

        # Determinación de sentido según columna Sentido o código de Puerta
        puerta_actual = puerta_nominal
        es_salida = False
        if "sentido" in col_map:
            s_txt = str(row.get(col_map["sentido"], "")).strip().lower()
            if any(k in s_txt for k in ["salida", "out", "egreso"]):
                es_salida = True
            elif any(k in s_txt for k in ["entrada", "in", "ingreso"]):
                es_salida = False
            elif puerta_actual:
                p_txt = puerta_actual.lower()
                es_salida = any(k in p_txt for k in ["out", "salida", "egreso"])
        elif puerta_actual:
            p_txt = puerta_actual.lower()
            es_salida = any(k in p_txt for k in ["out", "salida", "egreso"])

        if "sentido" in col_map or (puerta_actual and ("in" in puerta_actual.lower() or "out" in puerta_actual.lower())):
            if es_salida:
                door_out = puerta_actual
                door_in = None
                us_dt = event_time
                pe_dt = None
                salida_imputada = True   # Salida real registrada (1 para agregación en vista indexada)
                entrada_imputada = False
            else:
                door_in = puerta_actual
                door_out = None
                pe_dt = event_time
                us_dt = None
                salida_imputada = False  # Ingreso real registrado (0 para agregación en vista indexada)
                entrada_imputada = False
        else:
            entrada_imputada = bool(pe_dt is None and us_dt is not None)
            salida_imputada = bool(us_dt is None and pe_dt is not None)
        permanencia_min = None
        if pe_dt and us_dt and us_dt > pe_dt:
            permanencia_min = round((us_dt - pe_dt).total_seconds() / 60, 2)

        alerta_coherencia = bool(pe_dt and us_dt and pe_dt > us_dt)
        estamento_val = str(row.get(col_map.get("estamento", ""), "Estudiante")).strip() if "estamento" in col_map else "Estudiante"
        if estamento_val in ("", "nan", "None"):
            estamento_val = "Estudiante"

        # Conteo real de marcajes diarios por persona/fecha
        f_key = str(fecha_val).strip()[:10]
        conteo_real = 1
        if raw_id and f_key:
            conteo_real = max(marcajes_por_persona_dia.get((f_key, raw_id), 1), 1)

        dto = AttendanceEventDTO(
            time=event_time,
            espacio_id=espacio_id,
            person_id_hash=person_hash,
            door_entrada=door_in,
            door_salida=door_out,
            primera_entrada=pe_dt,
            ultima_salida=us_dt,
            salida_imputada=salida_imputada,
            entrada_imputada=entrada_imputada,
            permanencia_min=permanencia_min,
            marcajes_totales=conteo_real,
            alerta_coherencia_fechas=alerta_coherencia,
            alerta_marcajes=bool(conteo_real > 3),
            carrera=carrera_res,
            facultad=facultad_res,
        )
        setattr(dto, "estamento", estamento_val)
        dtos.append(dto)

    if modo_enlace == "mandatorio" and carreras_no_catalogadas > 0:
        pct = (carreras_catalogadas / len(df)) * 100 if len(df) > 0 else 0
        raise HTTPException(
            status_code=422,
            detail=(
                f"Modo mandatorio exige 100% de cruce curricular. Coincidencia actual: {pct:.1f}% "
                f"({carreras_catalogadas}/{len(df)}). Se encontraron {carreras_no_catalogadas} registros "
                f"sin carrera válida. Primeros huérfanos: {', '.join(huerfanos[:5])}"
            )
        )

    return dtos, carreras_catalogadas, carreras_no_catalogadas


def _parse_uct_dt_fast(val):
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime.combine(val, datetime.min.time())
    val_s = str(val).strip()
    if not val_s or val_s.lower() in ("null", "none", "nan", ""):
        return None
    try:
        return datetime.fromisoformat(val_s.split(".")[0])
    except Exception:
        try:
            return pd.to_datetime(val_s).to_pydatetime()
        except Exception:
            return None


def _parse_uct_date_fast(val):
    dt = _parse_uct_dt_fast(val)
    return dt.date() if dt else None


def determinar_facultad_uct(carr_nombre: Optional[str]) -> str:
    """Mapea una carrera a su facultad oficial de la UCT."""
    if not carr_nombre:
        return "Facultad UCT"
    c_norm = carr_nombre.upper()
    if any(k in c_norm for k in ["TÉCNICO", "TECNICO"]):
        return "Dirección Técnica Universitaria"
    if any(k in c_norm for k in ["INGENIERÍA CIVIL", "INGENIERIA DE EJECUCION", "INGENIERÍA ELÉCTRICA", "INGENIERÍA EN CONSTRUCCIÓN", "GEOLOGÍA"]):
        return "Facultad de Ingeniería"
    if any(k in c_norm for k in ["MEDICINA", "KINESIOLOGÍA", "FONOAUDIOLOGÍA", "NUTRICIÓN", "TERAPIA OCUPACIONAL", "QUÍMICA Y FARMACIA", "TECNOLOGÍA MÉDICA"]):
        return "Facultad de Ciencias de la Salud"
    if any(k in c_norm for k in ["PEDAGOGÍA", "PED.EN", "EDUCACIÓN", "EDUCACION"]):
        return "Facultad de Educación"
    if any(k in c_norm for k in ["DERECHO", "CIENCIA POLÍTICA"]):
        return "Facultad de Ciencias Jurídicas"
    if any(k in c_norm for k in ["COMERCIAL", "ADMINISTRACIÓN", "ADMINISTRACION", "CONTADOR"]):
        return "Facultad de Ciencias Económicas y Administrativas"
    if any(k in c_norm for k in ["ARQUITECTURA", "DISEÑO", "ARTES"]):
        return "Facultad de Arquitectura, Artes y Diseño"
    if any(k in c_norm for k in ["AGRONOMÍA", "ACUICULTURA", "FORESTAL", "VETERINARIA", "RECURSOS NATURALES", "BIOLOGIA EN GESTION"]):
        return "Facultad de Recursos Naturales"
    if any(k in c_norm for k in ["SOCIOLOGÍA", "ANTROPOLOGÍA", "ARQUEOLOGÍA", "TRABAJO SOCIAL", "PSICOLOGÍA", "GEOGRAFÍA", "TRADUCCIÓN"]):
        return "Facultad de Ciencias Sociales y Humanidades"
    if any(k in c_norm for k in ["TEOLOGÍA", "FILOSOFÍA", "RELIGIÓN"]):
        return "Facultad de Ciencias Religiosas y Filosofía"
    return "Facultad de Ingeniería" if "INGENIERÍA" in c_norm else "Facultad UCT"


async def procesar_archivo_institucional_uct(
    file_source: Any,
    filename: str,
    db: AsyncSession,
    modo_solapamiento: str = "merge",
    usuario_id: Optional[int] = None,
    job_id: Optional[uuid.UUID] = None,
    espacio_id: int = 1,
) -> dict:
    """
    Carga de forma transaccional y topológica el modelo institucional UCT (11 tablas)
    respetando nombres exactos, claves foráneas, SCD-2 para historial de situaciones
    y anonimización / cifrado según Ley N° 21.719. Sincroniza simultáneamente
    'dim_estudiante_carrera' para habilitar cruces curriculares inmediatos.
    """
    import openpyxl

    if isinstance(file_source, (str, Path)):
        wb = await asyncio.to_thread(openpyxl.load_workbook, file_source, data_only=True)
        with open(file_source, "rb") as f:
            f_bytes = f.read()
        file_hash = calcular_hash_archivo(f_bytes)
    else:
        wb = await asyncio.to_thread(openpyxl.load_workbook, io.BytesIO(file_source), data_only=True)
        file_hash = calcular_hash_archivo(file_source)

    if not job_id:
        job_id = uuid.uuid4()

    eliminados = 0
    if modo_solapamiento == "overwrite":
        logger.info("[ingesta_institucional] Modo overwrite detectado. Purgando tablas institucionales...")
        await db.execute(delete(DimEstudianteCarrera))
        await db.execute(delete(InstitucionalEstudianteCarrera))
        await db.execute(delete(InstitucionalEstudiante))
        await db.execute(delete(InstitucionalCarreraCampus))
        await db.execute(delete(InstitucionalCarreraPrograma))
        await db.execute(delete(InstitucionalTipoCarrera))
        await db.execute(delete(InstitucionalSituacionAlumno))
        await db.execute(delete(InstitucionalViasIngreso))
        await db.execute(delete(InstitucionalAmbiente))
        await db.execute(delete(InstitucionalEdificios))
        await db.execute(delete(InstitucionalTipoInmueble))
        await db.execute(delete(InstitucionalCampus))
        await db.flush()

    # 1. CAMPUS
    campus_ids = set()
    campus_items = []
    if "CAMPUS" in wb.sheetnames:
        ws_camp = wb["CAMPUS"]
        res_c = await db.execute(select(InstitucionalCampus.camp_codigo_campus))
        camp_existentes = set(res_c.scalars().all())
        campus_ids.update(camp_existentes)
        for r in list(ws_camp.iter_rows(values_only=True))[3:]:
            if r[0] is not None and str(r[0]).strip().isdigit():
                c_id = int(str(r[0]).strip())
                campus_ids.add(c_id)
                if c_id not in camp_existentes:
                    camp_existentes.add(c_id)
                    campus_items.append(
                        InstitucionalCampus(
                            camp_codigo_campus=c_id,
                            camp_campus=str(r[1] or "").strip(),
                            camp_direccion=str(r[2] or "").strip() or None,
                            camp_vigente=str(r[3] or "S").strip()[:1],
                            camp_fecha_registro=_parse_uct_dt_fast(r[4]),
                            camp_usuario=str(r[5] or "").strip() or None,
                        )
                    )
        if campus_items:
            db.add_all(campus_items)
            await db.flush()

    # 2. TIPO_INMUEBLE
    ti_items = []
    if "relacionadas con ambiente" in wb.sheetnames:
        ws_ti = wb["relacionadas con ambiente"]
        res_ti = await db.execute(select(InstitucionalTipoInmueble.tiin_codigo))
        tiin_existentes = set(res_ti.scalars().all())
        for r in list(ws_ti.iter_rows(values_only=True))[3:]:
            if r[0] is None:
                continue
            val_0 = str(r[0]).strip()
            if not val_0.isdigit():
                if "TABLA:" in val_0.upper():
                    break
                continue
            tiin_cod = int(val_0)
            if tiin_cod not in tiin_existentes:
                tiin_existentes.add(tiin_cod)
                ti_items.append(
                    InstitucionalTipoInmueble(
                        tiin_codigo=tiin_cod,
                        tiin_nombre=str(r[1] or "").strip(),
                        tiin_descripcion=str(r[2] or "").strip() or None,
                        tiin_vigente=str(r[3] or "S").strip()[:1],
                        usuario_mod=str(r[4] or "").strip() or None,
                        fecha_mod=_parse_uct_dt_fast(r[5]),
                    )
                )
        if ti_items:
            db.add_all(ti_items)
            await db.flush()

    # 3. EDIFICIOS
    ed_items = []
    if "EDIFICIOS" in wb.sheetnames:
        ws_ed = wb["EDIFICIOS"]
        res_ed = await db.execute(select(InstitucionalEdificios.edif_codigo_edificio))
        edif_existentes = set(res_ed.scalars().all())
        ed_rows = [r for r in list(ws_ed.iter_rows(values_only=True))[3:] if r[0] is not None and str(r[0]).strip().isdigit()]
        needed_camp_fks = {int(str(r[1]).strip()) for r in ed_rows if r[1] is not None and str(r[1]).strip().isdigit()}
        missing_camp = needed_camp_fks - campus_ids
        if missing_camp:
            for mc in missing_camp:
                db.add(InstitucionalCampus(
                    camp_codigo_campus=mc,
                    camp_campus=f"CAMPUS EXTERNO / NO ESPECIFICADO {mc}",
                    camp_vigente="N",
                    camp_usuario="sistema_ingesta",
                ))
                campus_ids.add(mc)
            await db.flush()

        for r in ed_rows:
            e_cod = int(str(r[0]).strip())
            if e_cod not in edif_existentes:
                edif_existentes.add(e_cod)
                ed_items.append(
                    InstitucionalEdificios(
                        edif_codigo_edificio=e_cod,
                        camp_codigo_campus=int(str(r[1]).strip()),
                        edif_edificio=str(r[2] or "").strip(),
                        edif_vigente=str(r[3] or "S").strip()[:1],
                        edif_observacion=str(r[4] or "").strip() or None,
                        edif_fecha_registro=_parse_uct_dt_fast(r[5]),
                        edif_usuario=str(r[6] or "").strip() or None,
                    )
                )
        if ed_items:
            db.add_all(ed_items)
            await db.flush()

    # 4. AMBIENTE
    amb_items = []
    if "AMBIENTE" in wb.sheetnames:
        ws_amb = wb["AMBIENTE"]
        res_amb = await db.execute(select(InstitucionalAmbiente.ambi_codigo))
        ambi_existentes = set(res_amb.scalars().all())
        for r in list(ws_amb.iter_rows(values_only=True))[3:]:
            if r[0] is not None and str(r[0]).strip().isdigit():
                amb_cod = int(str(r[0]).strip())
                if amb_cod not in ambi_existentes:
                    ambi_existentes.add(amb_cod)
                    amb_items.append(
                        InstitucionalAmbiente(
                            ambi_codigo=amb_cod,
                            camp_codigo=int(str(r[1]).strip()) if r[1] is not None and str(r[1]).strip().isdigit() else None,
                            inmu_codigo=int(str(r[2]).strip()) if r[2] is not None and str(r[2]).strip().isdigit() else None,
                            nive_codigo=int(str(r[3]).strip()) if r[3] is not None and str(r[3]).strip().isdigit() else None,
                            tami_codigo=int(str(r[4]).strip()) if r[4] is not None and str(r[4]).strip().isdigit() else None,
                            ambi_nombre=str(r[5] or "").strip(),
                            ambi_sigla_nuevo=str(r[6] or "").strip() or None,
                            ambi_vigente=str(r[7] or "S").strip()[:1],
                            usuario_mod=str(r[8] or "").strip() if len(r) > 8 and r[8] else None,
                            fecha_mod=_parse_uct_dt_fast(r[9]) if len(r) > 9 else None,
                        )
                    )
        if amb_items:
            db.add_all(amb_items)
            await db.flush()

    # 5. TIPO_CARRERA / CLASIFICACION_CARRERA
    tc_items = []
    if "relacio con carrera_programa" in wb.sheetnames:
        ws_tc = wb["relacio con carrera_programa"]
        tc_rows = list(ws_tc.iter_rows(values_only=True))[3:]
        tcar_dict = {}
        clac_dict = {}
        for r in tc_rows:
            if r[0] is not None and str(r[0]).strip().isdigit():
                tcar_dict[int(str(r[0]).strip())] = (str(r[1] or "").strip(), str(r[2] or "").strip())
            if len(r) > 6 and r[6] is not None and str(r[6]).strip().isdigit():
                clac_dict[int(str(r[6]).strip())] = (
                    str(r[7] or "").strip(),
                    str(r[8] or "").strip() if len(r) > 8 else None,
                    str(r[9] or "").strip() if len(r) > 9 else None,
                    _parse_uct_dt_fast(r[10]) if len(r) > 10 else None,
                )

        fk_pairs = set()
        if "CARRERA_PROGRAMA" in wb.sheetnames:
            ws_cp_pre = wb["CARRERA_PROGRAMA"]
            for r in list(ws_cp_pre.iter_rows(values_only=True))[3:]:
                if r[0] is not None and len(r) > 2 and r[1] is not None and r[2] is not None:
                    if str(r[1]).strip().isdigit() and str(r[2]).strip().isdigit():
                        fk_pairs.add((int(str(r[1]).strip()), int(str(r[2]).strip())))

        res_tc = await db.execute(select(InstitucionalTipoCarrera.tcar_codigo, InstitucionalTipoCarrera.clac_codigo))
        tc_existentes = set(res_tc.all())
        for tcar_c, clac_c in fk_pairs:
            if (tcar_c, clac_c) not in tc_existentes:
                tc_existentes.add((tcar_c, clac_c))
                t_nom, t_tip = tcar_dict.get(tcar_c, ("PREGRADO", "1"))
                c_nom, c_desc, c_user, c_fec = clac_dict.get(clac_c, ("CARRERA", "CARRERA PROFESIONAL", "MIGRACION", None))
                tc_items.append(
                    InstitucionalTipoCarrera(
                        tcar_codigo=tcar_c,
                        clac_codigo=clac_c,
                        tcar_nombre=t_nom,
                        tcar_tipo=t_tip,
                        clac_nombre=c_nom,
                        clac_descripcion=c_desc,
                        usuario_mod=c_user,
                        fecha_mod=c_fec,
                    )
                )
        if tc_items:
            db.add_all(tc_items)
            await db.flush()

    # 6. CARRERA_PROGRAMA
    cp_items = []
    carrera_map = {}
    if "CARRERA_PROGRAMA" in wb.sheetnames:
        ws_cp = wb["CARRERA_PROGRAMA"]
        res_cp = await db.execute(select(InstitucionalCarreraPrograma.carr_codigo, InstitucionalCarreraPrograma.carr_nombre))
        carr_existentes_rows = res_cp.all()
        carr_existentes = {r[0] for r in carr_existentes_rows}
        carrera_map.update({r[0]: r[1] for r in carr_existentes_rows})
        for r in list(ws_cp.iter_rows(values_only=True))[3:]:
            if r[0] is not None and str(r[0]).strip().isdigit():
                c_cod = int(str(r[0]).strip())
                c_nom = str(r[3] or "").strip()
                carrera_map[c_cod] = c_nom
                if c_cod not in carr_existentes:
                    carr_existentes.add(c_cod)
                    cp_items.append(
                        InstitucionalCarreraPrograma(
                            carr_codigo=c_cod,
                            tcar_codigo=int(str(r[1]).strip()) if r[1] is not None and str(r[1]).strip().isdigit() else None,
                            clac_codigo=int(str(r[2]).strip()) if r[2] is not None and str(r[2]).strip().isdigit() else None,
                            carr_nombre=c_nom,
                            uaca_codigo=int(str(r[4]).strip()) if r[4] is not None and str(r[4]).strip().isdigit() else None,
                            uaca_codigo_dicta=int(str(r[5]).strip()) if r[5] is not None and str(r[5]).strip().isdigit() else None,
                            usuario_mod=str(r[6] or "").strip() or None,
                            fecha_mod=_parse_uct_dt_fast(r[7]),
                        )
                    )
        if cp_items:
            db.add_all(cp_items)
            await db.flush()

    # 7. CARRERA_CAMPUS (deduplicada)
    cc_items = []
    if "CARRERA_CAMPUS" in wb.sheetnames:
        ws_cc = wb["CARRERA_CAMPUS"]
        res_cc = await db.execute(select(InstitucionalCarreraCampus.carr_codigo, InstitucionalCarreraCampus.camp_codigo))
        seen_cc = set(res_cc.all())
        for r in list(ws_cc.iter_rows(values_only=True))[3:]:
            if r[0] is not None and r[1] is not None and str(r[0]).strip().isdigit() and str(r[1]).strip().isdigit():
                pair = (int(str(r[0]).strip()), int(str(r[1]).strip()))
                if pair not in seen_cc:
                    seen_cc.add(pair)
                    cc_items.append(
                        InstitucionalCarreraCampus(
                            carr_codigo=pair[0],
                            camp_codigo=pair[1],
                            usuario_mod=str(r[2] or "").strip() or None,
                            fecha_mod=_parse_uct_dt_fast(r[3]),
                        )
                    )
        if cc_items:
            db.add_all(cc_items)
            await db.flush()

    # 8. SITUACION_ALUMNO
    sa_items = []
    situacion_map = {}
    if "SITUACION_ALUMNO" in wb.sheetnames:
        ws_sa = wb["SITUACION_ALUMNO"]
        res_sa = await db.execute(select(InstitucionalSituacionAlumno.salu_codigo, InstitucionalSituacionAlumno.salu_nombre))
        sa_existentes_rows = res_sa.all()
        sa_existentes = {r[0] for r in sa_existentes_rows}
        situacion_map.update({r[0]: r[1] for r in sa_existentes_rows})
        for r in list(ws_sa.iter_rows(values_only=True))[3:]:
            if r[0] is not None and str(r[0]).strip().isdigit():
                s_cod = int(str(r[0]).strip())
                s_nom = str(r[1] or "").strip()
                situacion_map[s_cod] = s_nom
                if s_cod not in sa_existentes:
                    sa_existentes.add(s_cod)
                    sa_items.append(
                        InstitucionalSituacionAlumno(
                            salu_codigo=s_cod,
                            salu_nombre=s_nom,
                        )
                    )
        if sa_items:
            db.add_all(sa_items)
            await db.flush()

    # 9. VIAS_INGRESO
    vi_items = []
    if "VIAS_INGRESO" in wb.sheetnames:
        ws_vi = wb["VIAS_INGRESO"]
        res_vi = await db.execute(select(InstitucionalViasIngreso.ving_codigo))
        vi_existentes = set(res_vi.scalars().all())
        for r in list(ws_vi.iter_rows(values_only=True))[3:]:
            if r[0] is not None and str(r[0]).strip().isdigit():
                v_cod = int(str(r[0]).strip())
                if v_cod not in vi_existentes:
                    vi_existentes.add(v_cod)
                    vi_items.append(
                        InstitucionalViasIngreso(
                            ving_codigo=v_cod,
                            ving_nombre=str(r[1] or "").strip(),
                            ving_descripcion=str(r[2] or "").strip() or None,
                            usuario_mod=str(r[3] or "").strip() or None,
                            fecha_mod=_parse_uct_dt_fast(r[4]),
                        )
                    )
        if vi_items:
            db.add_all(vi_items)
            await db.flush()

    # 10. ESTUDIANTE (Seudonimización y Cifrado Ley N° 21.719)
    est_items = []
    if "ESTUDIANTE" in wb.sheetnames:
        ws_est = wb["ESTUDIANTE"]
        res_est = await db.execute(select(InstitucionalEstudiante.estd_rut_hash))
        est_existentes = set(res_est.scalars().all())
        for r in list(ws_est.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                rut_raw = str(r[0]).strip()
                rut_h = pseudonymize_person(rut_raw)
                if rut_h not in est_existentes:
                    est_existentes.add(rut_h)
                    est_items.append(
                        InstitucionalEstudiante(
                            estd_rut_hash=rut_h,
                            estd_rut_cifrado=encrypt_api_key(rut_raw),
                            estd_dv=str(r[1] or "").strip()[:2] or None,
                            estd_paterno_cifrado=encrypt_api_key(str(r[2] or "").strip()) if r[2] else None,
                            estd_materno_cifrado=encrypt_api_key(str(r[3] or "").strip()) if r[3] else None,
                            estd_nombre1_cifrado=encrypt_api_key(str(r[4] or "").strip()) if r[4] else None,
                            estd_nombre2_cifrado=encrypt_api_key(str(r[5] or "").strip()) if r[5] else None,
                            sexo_codigo=str(r[6] or "").strip()[:10] if r[6] is not None else None,
                            estd_fecha_nac=_parse_uct_date_fast(r[7]),
                        )
                    )
        if est_items:
            batch_sz = 1000
            for i in range(0, len(est_items), batch_sz):
                db.add_all(est_items[i : i + batch_sz])
                await db.flush()

    # 11. ESTUDIANTE_CARRERA con SCD-2 y Sincronización en dim_estudiante_carrera
    ec_items = []
    dim_items = []
    ahora = datetime.now()
    if "ESTUDIANTE_CARRERA" in wb.sheetnames:
        ws_ec = wb["ESTUDIANTE_CARRERA"]
        res_act = await db.execute(
            select(InstitucionalEstudianteCarrera).where(InstitucionalEstudianteCarrera.es_actual == True)
        )
        ec_actuales = {(item.estu_registro, item.carr_codigo): item for item in res_act.scalars().all()}

        res_dim = await db.execute(select(DimEstudianteCarrera.matricula))
        dim_existentes = set(res_dim.scalars().all())

        for r in list(ws_ec.iter_rows(values_only=True))[3:]:
            if r[0] is not None:
                reg_str = str(r[0]).strip()
                rut_str = str(r[1]).strip() if r[1] is not None else ""
                rut_h = pseudonymize_person(rut_str) if rut_str else None
                dv_s = str(r[2] or "").strip()[:2] or None
                c_cod = int(str(r[3]).strip()) if r[3] is not None and str(r[3]).strip().isdigit() else None
                p_cod = int(str(r[4]).strip()) if r[4] is not None and str(r[4]).strip().isdigit() else None
                m_cod = int(str(r[5]).strip()) if r[5] is not None and str(r[5]).strip().isdigit() else None
                s_cod = int(str(r[6]).strip()) if r[6] is not None and str(r[6]).strip().isdigit() else None
                v_cod = int(str(r[7]).strip()) if r[7] is not None and str(r[7]).strip().isdigit() else None
                a_ing = int(str(r[8]).strip()) if len(r) > 8 and r[8] is not None and str(r[8]).strip().isdigit() else None
                s_ing = int(str(r[9]).strip()) if len(r) > 9 and r[9] is not None and str(r[9]).strip().isdigit() else None
                t_imp = int(str(r[10]).strip()) if len(r) > 10 and r[10] is not None and str(r[10]).strip().isdigit() else None
                u_mod = str(r[11] or "").strip() or None if len(r) > 11 else None
                f_mod = _parse_uct_dt_fast(r[12]) if len(r) > 12 else None

                periodo = f"{a_ing}-{s_ing}" if a_ing and s_ing else "2026-1"
                clave_ec = (reg_str, c_cod)

                if clave_ec in ec_actuales:
                    prev = ec_actuales[clave_ec]
                    if prev.salu_codigo == s_cod and prev.periodo_academico == periodo and prev.plan_codigo == p_cod:
                        continue
                    prev.es_actual = False
                    prev.fecha_hasta = ahora

                nuevo_ec = InstitucionalEstudianteCarrera(
                    estu_registro=reg_str,
                    estd_rut_hash=rut_h,
                    estd_dv=dv_s,
                    carr_codigo=c_cod,
                    plan_codigo=p_cod,
                    men_codigo=m_cod,
                    salu_codigo=s_cod,
                    ving_codigo=v_cod,
                    estu_anho_ing=a_ing,
                    estu_semestre_ing=s_ing,
                    timp_codigo=t_imp,
                    periodo_academico=periodo,
                    fecha_desde=ahora,
                    fecha_hasta=None,
                    es_actual=True,
                    usuario_mod=u_mod,
                    fecha_mod=f_mod,
                )
                ec_items.append(nuevo_ec)
                ec_actuales[clave_ec] = nuevo_ec

                if reg_str not in dim_existentes:
                    dim_existentes.add(reg_str)
                    pid_h = pseudonymize_person(reg_str)
                    c_nom = carrera_map.get(c_cod, "Sin carrera catalogada")
                    dim_items.append(
                        DimEstudianteCarrera(
                            person_id_hash=pid_h,
                            matricula=reg_str,
                            rut_hash=rut_h,
                            carr_codigo=str(c_cod) if c_cod else None,
                            carr_nombre=c_nom,
                            facultad=determinar_facultad_uct(c_nom),
                            anho_ingreso=a_ing,
                            estamento="Estudiante",
                        )
                    )

        batch_sz = 1000
        for i in range(0, len(ec_items), batch_sz):
            db.add_all(ec_items[i : i + batch_sz])
            await db.flush()

        for i in range(0, len(dim_items), batch_sz):
            db.add_all(dim_items[i : i + batch_sz])
            await db.flush()

    # Actualizar o persistir IngestionJob
    stmt_j = select(IngestionJob).where(IngestionJob.job_id == job_id)
    res_j = await db.execute(stmt_j)
    job = res_j.scalars().first()
    if not job:
        job = IngestionJob(
            job_id=job_id,
            filename=filename,
            tipo="institucional_uct",
            estado="completed",
            registros_ok=len(ec_items),
            registros_error=0,
            creado_por=usuario_id,
            creado_en=datetime.now(timezone.utc),
            completado_en=datetime.now(timezone.utc),
            file_hash=file_hash,
            espacio_id=espacio_id,
            modo_solapamiento=modo_solapamiento,
        )
        db.add(job)
    else:
        job.estado = "completed"
        job.registros_ok = len(ec_items)
        job.completado_en = datetime.now(timezone.utc)

    await db.commit()

    total_filas = len(campus_items) + len(ed_items) + len(amb_items) + len(cp_items) + len(ec_items)
    logger.info(
        f"[ingesta_institucional] Job {job_id} completado con éxito: "
        f"{len(ec_items)} estudiantes carrera (SCD-2) e instituciones persistidas."
    )

    return {
        "job_id": job_id,
        "total_filas": total_filas,
        "estudiantes_carrera": len(ec_items),
        "dim_estudiantes": len(dim_items),
        "campus": len(campus_items),
        "edificios": len(ed_items),
        "ambientes": len(amb_items),
        "carreras": len(cp_items),
        "situaciones": len(sa_items),
        "eliminados": eliminados,
    }


# ---------------------------------------------------------------------------
# Procesamiento y Carga Atómica con Sobrescritura de Rango (RF04, RF30)
# ---------------------------------------------------------------------------
async def ejecutar_ingesta_atomica(
    file_bytes: bytes,
    filename: str,
    tipo: str,
    espacio_id: int,
    modo_solapamiento: str,
    clave_enlace: str,
    modo_enlace: str,
    db: AsyncSession,
    usuario_id: Optional[int] = None,
) -> IngestionProcessResponse:
    """
    Ejecuta el procesamiento definitivo bajo una sola transacción atómica (BEGIN TRANSACTION).
    En modo 'overwrite' purga el rango previo; en modo 'merge' inserta únicamente los no duplicados.
    """
    file_hash = calcular_hash_archivo(file_bytes)
    tipo_clean = tipo.strip().lower()

    if modo_solapamiento != "overwrite":
        stmt_prev = select(IngestionJob).where(
            IngestionJob.file_hash == file_hash,
            IngestionJob.estado == "completed",
        )
        res_prev = await db.execute(stmt_prev)
        prev = res_prev.scalars().first()
        if prev:
            raise HTTPException(
                status_code=409,
                detail=f"El archivo '{filename}' con hash {file_hash[:12]} ya fue procesado. Para actualizar use modo 'overwrite'.",
            )

    if es_archivo_institucional_uct(file_bytes) or tipo_clean == "institucional_uct":
        stats_inst = await procesar_archivo_institucional_uct(
            file_source=file_bytes,
            filename=filename,
            db=db,
            modo_solapamiento=modo_solapamiento,
            usuario_id=usuario_id,
            espacio_id=espacio_id,
        )
        await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id)
        return IngestionProcessResponse(
            job_id=str(stats_inst["job_id"]),
            status="completed",
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            registros_procesados=stats_inst["total_filas"],
            registros_insertados=stats_inst["estudiantes_carrera"],
            registros_eliminados=stats_inst.get("eliminados", 0),
            carreras_catalogadas=stats_inst["estudiantes_carrera"],
            carreras_no_catalogadas=0,
            file_hash=file_hash,
            detalle=(
                f"Esquema institucional UCT (11 tablas) cargado exitosamente. "
                f"{stats_inst['estudiantes_carrera']} estudiantes con trazabilidad SCD-2 "
                f"y sincronizados en el maestro analítico."
            ),
        )

    header_idx, df = await asyncio.to_thread(extraer_dataframe_archivo, file_bytes, filename, tipo_clean)
    if df.empty:
        raise HTTPException(status_code=400, detail="El archivo no contiene filas procesables.")

    job_id = uuid.uuid4()

    if tipo_clean in ("asistencia", "marcajes_torniquete"):
        dtos, cat_ok, cat_no = await _mapear_df_a_dtos_asistencia(
            df=df,
            espacio_id=espacio_id,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            db=db,
        )

        if not dtos:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron eventos válidos de asistencia con fecha y hora en el archivo. Si este archivo contiene un listado de estudiantes o matrículas, seleccione el tipo 'Maestro Curricular' en el Paso 1.",
            )

        min_ts = min(d.time for d in dtos) if dtos else None
        max_ts = max(d.time for d in dtos) if dtos else None

        # Ejecución dentro de una transacción atómica
        if db.in_transaction():
            stats = await AttendanceService.bulk_insert_events(
                db=db,
                dtos=dtos,
                modo_solapamiento=modo_solapamiento,
                espacio_id=espacio_id,
                fecha_min=min_ts,
                fecha_max=max_ts,
            )
            job = IngestionJob(
                job_id=job_id,
                filename=filename,
                tipo=tipo_clean,
                estado="completed",
                registros_ok=stats["insertados"],
                registros_error=0,
                creado_por=usuario_id,
                creado_en=datetime.now(timezone.utc),
                completado_en=datetime.now(timezone.utc),
                file_hash=file_hash,
                fecha_min=min_ts,
                fecha_max=max_ts,
                modo_solapamiento=modo_solapamiento,
                clave_enlace=clave_enlace,
                modo_enlace=modo_enlace,
                espacio_id=espacio_id,
            )
            db.add(job)
            await db.commit()
        else:
            async with db.begin():
                stats = await AttendanceService.bulk_insert_events(
                    db=db,
                    dtos=dtos,
                    modo_solapamiento=modo_solapamiento,
                    espacio_id=espacio_id,
                    fecha_min=min_ts,
                    fecha_max=max_ts,
                )
                job = IngestionJob(
                    job_id=job_id,
                    filename=filename,
                    tipo=tipo_clean,
                    estado="completed",
                    registros_ok=stats["insertados"],
                    registros_error=0,
                    creado_por=usuario_id,
                    creado_en=datetime.now(timezone.utc),
                    completado_en=datetime.now(timezone.utc),
                    file_hash=file_hash,
                    fecha_min=min_ts,
                    fecha_max=max_ts,
                    modo_solapamiento=modo_solapamiento,
                    clave_enlace=clave_enlace,
                    modo_enlace=modo_enlace,
                    espacio_id=espacio_id,
                )
                db.add(job)

        return IngestionProcessResponse(
            job_id=str(job_id),
            status="completed",
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            registros_procesados=len(dtos),
            registros_insertados=stats["insertados"],
            registros_eliminados=stats["eliminados"],
            carreras_catalogadas=cat_ok,
            carreras_no_catalogadas=cat_no,
            file_hash=file_hash,
            detalle=(
                f"Ingesta completada. {stats['insertados']} registros insertados."
                + (f" Se eliminaron {stats['eliminados']} registros previos por sobrescritura de rango." if stats["eliminados"] > 0 else "")
            ),
        )

    elif tipo_clean == "vehicular":
        col_map = {}
        for c in df.columns:
            cn = _normalize_str(c)
            if "fecha_hora" not in col_map and any(k in cn for k in ["fecha y hora", "hora", "fecha", "timestamp", "datetime"]):
                col_map["fecha_hora"] = c
            if "patente" not in col_map and any(k in cn for k in ["placa", "patente", "numero de matricula", "matricula"]):
                col_map["patente"] = c
            if "camara" not in col_map and any(k in cn for k in ["camara", "cámara", "dispositivo", "lpr"]):
                col_map["camara"] = c
            if "direccion" not in col_map and any(k in cn for k in ["sentido", "direccion", "dirección", "conduccion", "flujo"]):
                col_map["direccion"] = c
            if "tipo" not in col_map and any(k in cn for k in ["tipo de vehiculo", "tipo de vehículo", "tipo", "categoria"]):
                col_map["tipo"] = c
            if "marca" not in col_map and "marca" in cn:
                col_map["marca"] = c
            if "color" not in col_map and "color" in cn:
                col_map["color"] = c

        dtos_veh: List[VehicleEventDTO] = []
        veh_records = df.to_dict(orient="records")
        for row in veh_records:
            fh_val = str(row.get(col_map.get("fecha_hora", ""), "")).strip()
            if not fh_val or fh_val.lower() in ("nan", "none", ""):
                continue
            t_dt = _parse_fast_dt(fh_val)
            if not t_dt:
                continue

            patente_raw = str(row.get(col_map.get("patente", ""), "")).strip()
            es_unknown = not patente_raw or patente_raw.lower() in ("nan", "none", "unknown", "")
            if not es_unknown:
                p_hash, p_cifrada = encrypt_vehicle_patente(patente_raw)
                calidad = "ok"
            else:
                p_hash, p_cifrada = "unknown", "unknown"
                calidad = "unknown"

            camara_val = str(row.get(col_map.get("camara", ""), "LPR-01")).strip()
            dir_raw = str(row.get(col_map.get("direccion", ""), "")).strip().lower()
            if any(k in dir_raw for k in ["avanzar", "entrada", "in", "ingreso"]):
                direccion = "entrada"
            elif any(k in dir_raw for k in ["retroceder", "salida", "out", "egreso"]):
                direccion = "salida"
            else:
                direccion = "entrada"

            tipo_v = str(row.get(col_map.get("tipo", ""), "")).strip() or None
            marca_v = str(row.get(col_map.get("marca", ""), "")).strip() or None
            color_v = str(row.get(col_map.get("color", ""), "")).strip() or None

            dtos_veh.append(
                VehicleEventDTO(
                    time=t_dt,
                    espacio_id=espacio_id,
                    patente_hash=p_hash,
                    patente_cifrada=p_cifrada,
                    camara=camara_val if camara_val not in ("nan", "None", "") else "LPR-01",
                    direccion=direccion,
                    tipo_vehiculo=tipo_v if tipo_v not in ("nan", "None", "") else None,
                    marca=marca_v if marca_v not in ("nan", "None", "") else None,
                    color=color_v if color_v not in ("nan", "None", "") else None,
                    calidad_lectura=calidad,
                )
            )

        if not dtos_veh:
            raise HTTPException(
                status_code=400,
                detail="No se encontraron eventos vehiculares válidos con fecha y hora en el archivo.",
            )

        min_ts = min(d.time for d in dtos_veh) if dtos_veh else None
        max_ts = max(d.time for d in dtos_veh) if dtos_veh else None

        if db.in_transaction():
            stats = await VehicleService.bulk_insert_events(
                db=db,
                dtos=dtos_veh,
                modo_solapamiento=modo_solapamiento,
                espacio_id=espacio_id,
                fecha_min=min_ts,
                fecha_max=max_ts,
            )
            job = IngestionJob(
                job_id=job_id,
                filename=filename,
                tipo=tipo_clean,
                estado="completed",
                registros_ok=stats["insertados"],
                registros_error=0,
                creado_por=usuario_id,
                creado_en=datetime.now(timezone.utc),
                completado_en=datetime.now(timezone.utc),
                file_hash=file_hash,
                fecha_min=min_ts,
                fecha_max=max_ts,
                modo_solapamiento=modo_solapamiento,
                espacio_id=espacio_id,
            )
            db.add(job)
            await db.commit()
        else:
            async with db.begin():
                stats = await VehicleService.bulk_insert_events(
                    db=db,
                    dtos=dtos_veh,
                    modo_solapamiento=modo_solapamiento,
                    espacio_id=espacio_id,
                    fecha_min=min_ts,
                    fecha_max=max_ts,
                )
                job = IngestionJob(
                    job_id=job_id,
                    filename=filename,
                    tipo=tipo_clean,
                    estado="completed",
                    registros_ok=stats["insertados"],
                    registros_error=0,
                    creado_por=usuario_id,
                    creado_en=datetime.now(timezone.utc),
                    completado_en=datetime.now(timezone.utc),
                    file_hash=file_hash,
                    fecha_min=min_ts,
                    fecha_max=max_ts,
                    modo_solapamiento=modo_solapamiento,
                    espacio_id=espacio_id,
                )
                db.add(job)

        return IngestionProcessResponse(
            job_id=str(job_id),
            status="completed",
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            registros_procesados=len(dtos_veh),
            registros_insertados=stats["insertados"],
            registros_eliminados=stats["eliminados"],
            carreras_catalogadas=0,
            carreras_no_catalogadas=0,
            file_hash=file_hash,
            detalle=(
                f"Ingesta vehicular completada. {stats['insertados']} registros insertados."
                + (f" Se eliminaron {stats['eliminados']} registros previos por sobrescritura de rango." if stats["eliminados"] > 0 else "")
            ),
        )

    elif tipo_clean == "curricular":
        inserted = 0
        items_curriculares = []
        rut_col = None
        mat_col = None
        carr_col = None
        fac_col = None

        for c in df.columns:
            cn = _normalize_str(c)
            if not rut_col and any(k in cn for k in ["rut", "run", "cedula", "usuario"]):
                rut_col = c
            if not mat_col and any(k in cn for k in ["matricula", "estu_registro", "id_estudiante"]):
                mat_col = c
            if not carr_col and any(k in cn for k in ["carrera", "carr_nombre", "programa", "plan_estudios"]):
                carr_col = c
            if not fac_col and any(k in cn for k in ["facultad", "fac_nombre", "unidad_academica"]):
                fac_col = c

        # En modo overwrite purgar catálogo previo
        if modo_solapamiento == "overwrite":
            stmt_del_c = delete(DimEstudianteCarrera)
            await db.execute(stmt_del_c)

        curr_records = df.to_dict(orient="records")
        for r in curr_records:
            rut_val = str(r.get(rut_col, "")).strip() if rut_col else ""
            mat_val = str(r.get(mat_col, "")).strip() if mat_col else ""
            carr_nom = str(r.get(carr_col, "")).strip() if carr_col else None
            fac_nom = str(r.get(fac_col, "")).strip() if fac_col else None

            if rut_val.lower() in ("nan", "none", ""):
                rut_val = ""
            if mat_val.lower() in ("nan", "none", ""):
                mat_val = ""
            if carr_nom and carr_nom.lower() in ("nan", "none", ""):
                carr_nom = None
            if fac_nom and fac_nom.lower() in ("nan", "none", ""):
                fac_nom = None

            if not rut_val and not mat_val:
                continue

            # Priorizar matrícula sobre RUT para enlace determinístico con torniquetes peatonales
            pid = pseudonymize_person(mat_val or rut_val)
            item = DimEstudianteCarrera(
                person_id_hash=pid,
                matricula=mat_val or None,
                rut_hash=pseudonymize_person(rut_val) if rut_val else None,
                carr_codigo=None,
                carr_nombre=carr_nom,
                facultad=fac_nom,
                estamento="Estudiante",
            )
            items_curriculares.append(item)
            inserted += 1

        job = IngestionJob(
            job_id=job_id,
            filename=filename,
            tipo=tipo_clean,
            estado="completed",
            registros_ok=inserted,
            registros_error=0,
            creado_por=usuario_id,
            creado_en=datetime.now(timezone.utc),
            completado_en=datetime.now(timezone.utc),
            file_hash=file_hash,
            espacio_id=espacio_id,
        )

        batch_size = 5000
        for i in range(0, len(items_curriculares), batch_size):
            chunk = items_curriculares[i:i + batch_size]
            db.add_all(chunk)
            await db.flush()

        db.add(job)
        await db.commit()

        return IngestionProcessResponse(
            job_id=str(job_id),
            status="completed",
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            registros_procesados=len(df),
            registros_insertados=inserted,
            registros_eliminados=0,
            carreras_catalogadas=inserted,
            carreras_no_catalogadas=0,
            file_hash=file_hash,
            detalle=f"Maestro curricular cargado exitosamente. {inserted} registros de estudiantes procesados.",
        )

    else:
        # Fallback para custom u otros módulos
        job = IngestionJob(
            job_id=job_id,
            filename=filename,
            tipo=tipo_clean,
            estado="completed",
            registros_ok=len(df),
            registros_error=0,
            creado_por=usuario_id,
            creado_en=datetime.now(timezone.utc),
            completado_en=datetime.now(timezone.utc),
            file_hash=file_hash,
            espacio_id=espacio_id,
        )
        if db.in_transaction():
            db.add(job)
            await db.commit()
        else:
            async with db.begin():
                db.add(job)

        return IngestionProcessResponse(
            job_id=str(job_id),
            status="completed",
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
            registros_procesados=len(df),
            registros_insertados=len(df),
            registros_eliminados=0,
            carreras_catalogadas=0,
            carreras_no_catalogadas=0,
            file_hash=file_hash,
            detalle=f"Ingesta procesada para módulo {tipo_clean}.",
        )


# ---------------------------------------------------------------------------
# Enriquecimiento Curricular Retroactivo (RF30)
# ---------------------------------------------------------------------------
async def enriquecer_asistencia_retroactiva(
    db: AsyncSession,
    espacio_id: int = 1,
    clave_enlace: str = "auto",
) -> Dict[str, Any]:
    """
    Enriquece retroactivamente los eventos de asistencia que tengan 'Sin carrera catalogada'
    o carrera nula cruzando en caliente con 'dim_estudiante_carrera' (RF30).
    """
    tipo_enlace = clave_enlace.lower().strip() if clave_enlace else "auto"
    stmt_cat = select(DimEstudianteCarrera)
    res_cat = await db.execute(stmt_cat)
    estudiantes = res_cat.scalars().all()

    if not estudiantes:
        return {
            "status": "warning",
            "espacio_id": espacio_id,
            "enriquecidos": 0,
            "pendientes": 0,
            "detalle": "El catálogo dim_estudiante_carrera se encuentra vacío. Cargue previamente el maestro curricular.",
        }

    por_pid = {}
    por_rut = {}
    por_mat = {}

    for e in estudiantes:
        if e.person_id_hash:
            por_pid[e.person_id_hash] = (e.carr_nombre, e.facultad)
        if e.rut_hash:
            por_rut[e.rut_hash] = (e.carr_nombre, e.facultad)
        if e.matricula:
            m_norm = str(e.matricula).strip().lower()
            por_mat[m_norm] = (e.carr_nombre, e.facultad)
            por_pid[pseudonymize_person(m_norm)] = (e.carr_nombre, e.facultad)

    stmt_ev = (
        select(EventoAsistencia)
        .where(
            EventoAsistencia.espacio_id == espacio_id,
            (EventoAsistencia.carrera == "Sin carrera catalogada") | (EventoAsistencia.carrera.is_(None)),
        )
    )
    res_ev = await db.execute(stmt_ev)
    eventos = res_ev.scalars().all()

    enriquecidos = 0
    pendientes = 0

    for ev in eventos:
        if tipo_enlace == "pid":
            match = por_pid.get(ev.person_id_hash)
        elif tipo_enlace == "rut":
            match = por_rut.get(ev.person_id_hash)
        else:
            match = por_pid.get(ev.person_id_hash) or por_rut.get(ev.person_id_hash)
        if match:
            carr, fac = match
            if carr:
                ev.carrera = carr
                if fac:
                    ev.facultad = fac
                enriquecidos += 1
            else:
                pendientes += 1
        else:
            pendientes += 1

    await db.commit()

    return {
        "status": "completed",
        "espacio_id": espacio_id,
        "enriquecidos": enriquecidos,
        "pendientes": pendientes,
        "total_evaluados": len(eventos),
        "detalle": f"Proceso retroactivo finalizado. Se enriquecieron {enriquecidos} eventos con su carrera oficial.",
    }


# ---------------------------------------------------------------------------
# Pipeline Asíncrono de Ingesta por Lotes con Semáforo (RF01, RF05)
# ---------------------------------------------------------------------------
# Semáforo global: limita a 1 ingesta concurrente activa (las demás quedan en 'queued')
_semaforo_ingesta = asyncio.Semaphore(1)


async def limpiar_trabajos_ingesta_huerfanos() -> int:
    """
    Marca como 'failed' los trabajos huérfanos que quedaron en 'processing' o 'queued'
    debido a un reinicio o detención del servidor API.
    """
    async with AsyncSessionLocal() as db:
        stmt = select(IngestionJob).where(IngestionJob.estado.in_(["processing", "queued"]))
        res = await db.execute(stmt)
        huerfanos = res.scalars().all()
        if not huerfanos:
            return 0
        ahora = datetime.now(timezone.utc)
        for job in huerfanos:
            job.estado = "failed"
            job.error_detail = "Trabajo huérfano interrumpido por reinicio del servidor API."
            job.completado_en = ahora
        await db.commit()
        logger.warning(f"[ingesta] Se marcaron {len(huerfanos)} trabajos huérfanos como 'failed'.")
        return len(huerfanos)


async def invalidar_caches_recinto_y_actualizar_predicciones(espacio_id: int) -> None:
    """
    Invalida las cachés en memoria del recinto tras una ingesta completada y actualiza predicciones.
    """
    try:
        from app.core.cache import invalidar_cache_por_espacio
        await invalidar_cache_por_espacio(espacio_id)
        logger.info(f"[ingesta] Caché analítica invalidada para recinto {espacio_id}.")
    except Exception as exc:
        logger.debug(f"[ingesta] Error invalidando caché analítica: {exc}")

    try:
        from app.ml.gestor_modelos import _cache_modelos_memoria
        _cache_modelos_memoria.clear()
        logger.info(f"[ingesta] Caché de modelos en memoria invalidada para recinto {espacio_id}.")
    except Exception as exc:
        logger.warning(f"[ingesta] Error invalidando caché de modelos: {exc}")

    try:
        from app.api.v1.endpoints.chat import _cache_resultados_herramientas, CHAT_CACHE
        _cache_resultados_herramientas.clear()
        CHAT_CACHE.clear()
        logger.info("[ingesta] Caché de herramientas analíticas de chat invalidada.")
    except Exception:
        pass

    try:
        from app.ml.prophet_service import predict_next_7_days
        await asyncio.to_thread(predict_next_7_days, espacio_id=espacio_id, recalcular=True)
        logger.info(f"[ingesta] Predicciones de 7 días actualizadas para espacio {espacio_id}.")
    except Exception as exc:
        logger.debug(f"[ingesta] Actualización de predicciones omitida o pendiente de modelos: {exc}")


def _iterar_lotes_dataframe(ruta_archivo: Path, tipo: str, chunk_size: int = 10000):
    """
    Genera DataFrames por lotes de tamaño chunk_size a partir de un archivo CSV o Excel.
    """
    suffix = ruta_archivo.suffix.lower()
    tipo_clean = tipo.strip().lower()
    keywords = _get_target_keywords_set(tipo_clean)

    if suffix == ".csv":
        with open(ruta_archivo, "rb") as f:
            header_sample = f.read(65536)
        best_row, _, _ = _detect_header_row_csv(header_sample, keywords, max_rows=5)

        encodings = ["utf-8-sig", "utf-8", "latin-1", "iso-8859-1"]
        chosen_enc = "utf-8-sig"
        for enc in encodings:
            try:
                header_sample.decode(enc)
                chosen_enc = enc
                break
            except UnicodeDecodeError:
                continue

        for chunk in pd.read_csv(
            ruta_archivo,
            skiprows=best_row,
            encoding=chosen_enc,
            dtype=str,
            keep_default_na=False,
            chunksize=chunk_size,
            low_memory=False,
        ):
            yield chunk
    else:
        with open(ruta_archivo, "rb") as f:
            file_bytes = f.read()
        best_row, df_full, _ = _detect_header_row_excel(file_bytes, keywords, max_rows=None)
        total_len = len(df_full)
        for i in range(0, total_len, chunk_size):
            chunk = df_full.iloc[i : i + chunk_size].copy()
            yield chunk
        del df_full
        gc.collect()


def _procesar_lote_asistencia_sync(
    lote_df: pd.DataFrame,
    espacio_id: int,
    clave_enlace: str,
    modo_enlace: str,
    maestro_estudiantes: Dict[str, Any],
) -> List[AttendanceEventDTO]:
    """
    Procesa un lote de asistencia eliminando PII y aplicando seudonimización (Ley N° 21.719).
    """
    # PRIVACIDAD ESTRICTA: Supresión inmediata de columnas personales
    cols_pii = [
        c for c in lote_df.columns
        if any(k in _normalize_str(c) for k in ["persona", "nombre", "telefono", "teléfono", "correo", "email"])
    ]
    lote_df.drop(columns=cols_pii, errors="ignore", inplace=True)

    col_map = {}
    norm_detected = [_normalize_str(c) for c in lote_df.columns]
    for orig_c, c_norm in zip(lote_df.columns, norm_detected):
        if "fecha" not in col_map and any(k in c_norm for k in ["fecha", "date", "dia"]):
            col_map["fecha"] = orig_c
        if "primera_entrada" not in col_map and any(k in c_norm for k in ["primera entrada", "first in", "in time"]):
            col_map["primera_entrada"] = orig_c
        if "ultima_salida" not in col_map and any(k in c_norm for k in ["ultima salida", "última salida", "last out", "out time"]):
            col_map["ultima_salida"] = orig_c
        if "hora_general" not in col_map and any(k in c_norm for k in ["hora", "time", "hora_marcaje", "horamarcaje"]):
            col_map["hora_general"] = orig_c
        if "puerta_gral" not in col_map and any(k in c_norm for k in ["puerta", "door", "torniquete"]):
            col_map["puerta_gral"] = orig_c
        if "sentido" not in col_map and any(k in c_norm for k in ["sentido", "direccion", "dirección"]):
            col_map["sentido"] = orig_c
        if "matricula" not in col_map and any(k in c_norm for k in ["matricula", "matrícula", "estu_registro"]):
            col_map["matricula"] = orig_c
        if "rut" not in col_map and any(k in c_norm for k in ["rut", "run", "cedula"]):
            col_map["rut"] = orig_c
        if "id_visitante" not in col_map and any(k in c_norm for k in ["personid", "person_id"]):
            col_map["id_visitante"] = orig_c
        if "carrera" not in col_map and any(k in c_norm for k in ["carrera", "programa", "plan_estudios", "carr_nombre"]):
            col_map["carrera"] = orig_c
        if "facultad" not in col_map and "facultad" in c_norm:
            col_map["facultad"] = orig_c
        if "estamento" not in col_map and any(k in c_norm for k in ["estamento", "tipo_usuario", "rol", "categoria"]):
            col_map["estamento"] = orig_c

    records = lote_df.to_dict(orient="records")
    col_estamento_name = col_map.get("estamento", "")
    col_fecha_name = col_map.get("fecha", "")
    col_mat_name = col_map.get("matricula", "")
    col_rut_name = col_map.get("rut", "")
    col_id_name = col_map.get("id_visitante", "")

    marcajes_por_persona_dia = {}
    for r in records:
        if espacio_id == 1 and col_estamento_name:
            est_raw = str(r.get(col_estamento_name, "")).strip().lower()
            if est_raw != "estudiante":
                continue
        f_val = str(r.get(col_fecha_name, "")).strip()[:10]
        uid = str(r.get(col_mat_name, "")).strip() or str(r.get(col_rut_name, "")).strip() or str(r.get(col_id_name, "")).strip()
        if f_val and uid and uid.lower() not in ("nan", "none", "", "null"):
            clave = (f_val, uid)
            marcajes_por_persona_dia[clave] = marcajes_por_persona_dia.get(clave, 0) + 1

    dtos: List[AttendanceEventDTO] = []
    for idx, row in enumerate(records):
        if espacio_id == 1 and col_estamento_name:
            est_raw = str(row.get(col_estamento_name, "")).strip().lower()
            if est_raw != "estudiante":
                continue

        fecha_val = row.get(col_map.get("fecha", ""), "") if "fecha" in col_map else ""
        pe_val = row.get(col_map.get("primera_entrada", ""), "") if "primera_entrada" in col_map else ""
        us_val = row.get(col_map.get("ultima_salida", ""), "") if "ultima_salida" in col_map else ""
        hora_val = row.get(col_map.get("hora_general", ""), "") if "hora_general" in col_map else ""

        pe_dt = _parse_fast_dt(fecha_val, pe_val) if pe_val else None
        us_dt = _parse_fast_dt(fecha_val, us_val) if us_val else None
        event_time = pe_dt or us_dt or _parse_fast_dt(fecha_val, hora_val) or _parse_fast_dt(fecha_val)
        if not event_time:
            continue

        raw_id = (
            str(row.get(col_map.get("matricula", ""), "")).strip()
            or str(row.get(col_map.get("rut", ""), "")).strip()
            or str(row.get(col_map.get("id_visitante", ""), "")).strip()
        )
        if raw_id.lower() in ("nan", "none", "null"):
            raw_id = ""

        puerta_nominal = str(row.get(col_map.get("puerta_gral", ""), "")).strip() or None
        if puerta_nominal in ("", "nan", "None"):
            puerta_nominal = None

        if raw_id:
            person_hash = pseudonymize_person(raw_id)
        else:
            door_sample = puerta_nominal or "torniquete"
            person_hash = f"anon_{hashlib.sha256(f'{event_time}_{door_sample}_{idx}'.encode()).hexdigest()[:16]}"

        carrera_res = str(row.get(col_map.get("carrera", ""), "")).strip() or None
        facultad_res = str(row.get(col_map.get("facultad", ""), "")).strip() or None
        if carrera_res in ("nan", "None", ""):
            carrera_res = None
        if facultad_res in ("nan", "None", ""):
            facultad_res = None

        if not carrera_res and maestro_estudiantes:
            matched_est = None
            if clave_enlace in ("rut", "crosswalk") and "rut" in col_map:
                r_val = str(row.get(col_map["rut"], "")).strip()
                if r_val and r_val.lower() not in ("nan", "none", ""):
                    r_hash = pseudonymize_person(r_val)
                    matched_est = maestro_estudiantes.get(f"rut:{r_hash}")
            if not matched_est and clave_enlace in ("matricula", "crosswalk") and "matricula" in col_map:
                m_val = str(row.get(col_map["matricula"], "")).strip().lower()
                if m_val and m_val not in ("nan", "none", ""):
                    matched_est = maestro_estudiantes.get(f"mat:{m_val}")
            if not matched_est and raw_id:
                matched_est = maestro_estudiantes.get(f"pid:{person_hash}")
            if matched_est:
                carrera_res = matched_est.carr_nombre
                facultad_res = matched_est.facultad

        carrera_res = carrera_res or "Sin carrera catalogada"
        facultad_res = facultad_res or "Sin facultad"

        puerta_actual = puerta_nominal
        es_salida = False
        if "sentido" in col_map:
            s_txt = str(row.get(col_map["sentido"], "")).strip().lower()
            if any(k in s_txt for k in ["salida", "out", "egreso"]):
                es_salida = True
            elif any(k in s_txt for k in ["entrada", "in", "ingreso"]):
                es_salida = False
            elif puerta_actual:
                es_salida = any(k in puerta_actual.lower() for k in ["out", "salida", "egreso"])
        elif puerta_actual:
            es_salida = any(k in puerta_actual.lower() for k in ["out", "salida", "egreso"])

        if es_salida:
            door_in = None
            door_out = puerta_actual
            us_dt = event_time
            pe_dt = None
            salida_imputada = True
            entrada_imputada = False
        else:
            door_in = puerta_actual
            door_out = None
            pe_dt = event_time
            us_dt = None
            salida_imputada = False
            entrada_imputada = False

        permanencia_min = None
        if pe_dt and us_dt and us_dt > pe_dt:
            permanencia_min = round((us_dt - pe_dt).total_seconds() / 60.0, 2)

        f_str = event_time.strftime("%Y-%m-%d")
        marcajes_totales = marcajes_por_persona_dia.get((f_str, raw_id), 1) if raw_id else 1

        dto = AttendanceEventDTO(
            time=event_time,
            espacio_id=espacio_id,
            person_id_hash=person_hash,
            door_entrada=door_in,
            door_salida=door_out,
            primera_entrada=pe_dt,
            ultima_salida=us_dt,
            salida_imputada=salida_imputada,
            entrada_imputada=entrada_imputada,
            permanencia_min=float(permanencia_min) if permanencia_min is not None else None,
            marcajes_totales=marcajes_totales,
            alerta_coherencia_fechas=False,
            alerta_marcajes=marcajes_totales > 20,
            carrera=carrera_res,
            facultad=facultad_res,
        )
        setattr(dto, "estamento", str(row.get(col_estamento_name, "Estudiante")).strip() if col_estamento_name else "Estudiante")
        dtos.append(dto)
    return dtos


def _procesar_lote_vehicular_sync(
    lote_df: pd.DataFrame,
    espacio_id: int,
) -> List[VehicleEventDTO]:
    """
    Procesa un lote vehicular eliminando PII y cifrando patentes (Ley N° 21.719).
    """
    # PRIVACIDAD ESTRICTA: Supresión inmediata de PII
    cols_pii = [
        c for c in lote_df.columns
        if any(k in _normalize_str(c) for k in ["telefono", "teléfono", "lista de vehiculos", "lista de vehículos", "nombre", "correo", "email"])
    ]
    lote_df.drop(columns=cols_pii, errors="ignore", inplace=True)

    col_map = {}
    for c in lote_df.columns:
        cn = _normalize_str(c)
        if "fecha_hora" not in col_map and any(k in cn for k in ["fecha y hora", "hora", "fecha", "timestamp"]):
            col_map["fecha_hora"] = c
        if "patente" not in col_map and any(k in cn for k in ["placa", "patente", "numero de matricula", "matricula"]):
            col_map["patente"] = c
        if "camara" not in col_map and any(k in cn for k in ["camara", "cámara", "dispositivo", "lpr"]):
            col_map["camara"] = c
        if "direccion" not in col_map and any(k in cn for k in ["sentido", "direccion", "dirección", "conduccion"]):
            col_map["direccion"] = c
        if "tipo" not in col_map and any(k in cn for k in ["tipo de vehiculo", "tipo de vehículo", "tipo"]):
            col_map["tipo"] = c
        if "marca" not in col_map and "marca" in cn:
            col_map["marca"] = c
        if "color" not in col_map and "color" in cn:
            col_map["color"] = c

    dtos_veh: List[VehicleEventDTO] = []
    for row in lote_df.to_dict(orient="records"):
        fh_val = str(row.get(col_map.get("fecha_hora", ""), "")).strip()
        if not fh_val or fh_val.lower() in ("nan", "none", ""):
            continue
        t_dt = _parse_fast_dt(fh_val)
        if not t_dt:
            continue

        patente_raw = str(row.get(col_map.get("patente", ""), "")).strip()
        es_unknown = not patente_raw or patente_raw.lower() in ("nan", "none", "unknown", "")
        if not es_unknown:
            p_hash, p_cifrada = encrypt_vehicle_patente(patente_raw)
            calidad = "ok"
        else:
            p_hash, p_cifrada = "unknown", "unknown"
            calidad = "unknown"

        camara_val = str(row.get(col_map.get("camara", ""), "LPR-01")).strip()
        dir_raw = str(row.get(col_map.get("direccion", ""), "")).strip().lower()
        if any(k in dir_raw for k in ["avanzar", "entrada", "in", "ingreso"]):
            direccion = "entrada"
        elif any(k in dir_raw for k in ["retroceder", "salida", "out", "egreso"]):
            direccion = "salida"
        else:
            direccion = "entrada"

        tipo_v = str(row.get(col_map.get("tipo", ""), "")).strip() or None
        marca_v = str(row.get(col_map.get("marca", ""), "")).strip() or None
        color_v = str(row.get(col_map.get("color", ""), "")).strip() or None

        dtos_veh.append(
            VehicleEventDTO(
                time=t_dt,
                espacio_id=espacio_id,
                patente_hash=p_hash,
                patente_cifrada=p_cifrada,
                camara=camara_val if camara_val not in ("nan", "None", "") else "LPR-01",
                direccion=direccion,
                tipo_vehiculo=tipo_v if tipo_v not in ("nan", "None", "") else None,
                marca=marca_v if marca_v not in ("nan", "None", "") else None,
                color=color_v if color_v not in ("nan", "None", "") else None,
                calidad_lectura=calidad,
            )
        )
    return dtos_veh


async def procesar_archivo_por_lotes(
    job_id: uuid.UUID,
    ruta_archivo: Path,
    tipo: str,
    espacio_id: int,
    modo_solapamiento: str = "merge",
    clave_enlace: str = "rut",
    modo_enlace: str = "tolerante",
) -> None:
    """
    Procesa un archivo masivo por lotes de 10.000 registros, liberando memoria del DataFrame
    por lote y reportando progreso en tiempo real en IngestionJob (RF01, RF05).
    """
    async with AsyncSessionLocal() as db:
        job = await db.get(IngestionJob, job_id)
        if not job:
            logger.error(f"[ingesta] Job {job_id} no encontrado en base de datos.")
            return

        job.estado = "processing"
        await db.commit()

        tipo_clean = tipo.strip().lower()
        total_insertados = 0

        try:
            if es_archivo_institucional_uct(ruta_archivo) or tipo_clean == "institucional_uct":
                await procesar_archivo_institucional_uct(
                    file_source=ruta_archivo,
                    filename=ruta_archivo.name,
                    db=db,
                    modo_solapamiento=modo_solapamiento,
                    job_id=job_id,
                    espacio_id=espacio_id,
                )
                await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id)
                return

            # Precargar catálogo curricular una sola vez si es asistencia
            maestro_estudiantes = {}
            if tipo_clean in ("asistencia", "marcajes_torniquete"):
                stmt_m = select(DimEstudianteCarrera)
                res_m = await db.execute(stmt_m)
                for est in res_m.scalars().all():
                    if est.rut_hash:
                        maestro_estudiantes[f"rut:{est.rut_hash}"] = est
                    if est.matricula:
                        maestro_estudiantes[f"mat:{str(est.matricula).strip().lower()}"] = est
                    if est.person_id_hash:
                        maestro_estudiantes[f"pid:{est.person_id_hash}"] = est

            # Iterar por lotes de 10.000 filas
            for chunk_df in _iterar_lotes_dataframe(ruta_archivo, tipo_clean, chunk_size=10000):
                if chunk_df.empty:
                    del chunk_df
                    gc.collect()
                    continue

                if tipo_clean in ("asistencia", "marcajes_torniquete"):
                    dtos = await asyncio.to_thread(
                        _procesar_lote_asistencia_sync,
                        chunk_df,
                        espacio_id,
                        clave_enlace,
                        modo_enlace,
                        maestro_estudiantes,
                    )
                    if dtos:
                        stats = await AttendanceService.bulk_insert_events(
                            db=db,
                            dtos=dtos,
                            modo_solapamiento="merge",
                            espacio_id=espacio_id,
                        )
                        total_insertados += stats["insertados"]
                        job.registros_ok = total_insertados
                        await db.commit()
                    del dtos

                elif tipo_clean == "vehicular":
                    dtos_veh = await asyncio.to_thread(
                        _procesar_lote_vehicular_sync,
                        chunk_df,
                        espacio_id,
                    )
                    if dtos_veh:
                        stats = await VehicleService.bulk_insert_events(
                            db=db,
                            dtos=dtos_veh,
                            modo_solapamiento="merge",
                            espacio_id=espacio_id,
                        )
                        total_insertados += stats["insertados"]
                        job.registros_ok = total_insertados
                        await db.commit()
                    del dtos_veh

                elif tipo_clean == "curricular":
                    # Maestro curricular por lotes
                    items_lote = []
                    cols_pii = [c for c in chunk_df.columns if any(p in _normalize_str(c) for p in ["nombre", "telefono", "correo", "email"])]
                    chunk_df.drop(columns=cols_pii, errors="ignore", inplace=True)

                    rut_col = next((c for c in chunk_df.columns if any(k in _normalize_str(c) for k in ["rut", "run", "cedula"])), None)
                    mat_col = next((c for c in chunk_df.columns if any(k in _normalize_str(c) for k in ["matricula", "matrícula", "estu_registro"])), None)
                    carr_col = next((c for c in chunk_df.columns if any(k in _normalize_str(c) for k in ["carrera", "carr_nombre", "programa"])), None)
                    fac_col = next((c for c in chunk_df.columns if "facultad" in _normalize_str(c)), None)
                    anho_col = next((c for c in chunk_df.columns if any(k in _normalize_str(c) for k in ["anho", "año", "anio", "cohorte"])), None)

                    for r in chunk_df.to_dict(orient="records"):
                        rut_val = str(r.get(rut_col, "")).strip() if rut_col else ""
                        mat_val = str(r.get(mat_col, "")).strip() if mat_col else ""
                        carr_val = str(r.get(carr_col, "")).strip() if carr_col else None
                        fac_val = str(r.get(fac_col, "")).strip() if fac_col else None

                        if rut_val.lower() in ("nan", "none", ""):
                            rut_val = ""
                        if mat_val.lower() in ("nan", "none", ""):
                            mat_val = ""

                        if not rut_val and not mat_val:
                            continue

                        pid_hash = pseudonymize_person(mat_val or rut_val)
                        r_hash = pseudonymize_person(rut_val) if rut_val else None

                        anho_num = None
                        if anho_col:
                            try:
                                anho_num = int(float(str(r.get(anho_col, ""))))
                            except Exception:
                                anho_num = None

                        items_lote.append(
                            DimEstudianteCarrera(
                                person_id_hash=pid_hash,
                                matricula=mat_val or None,
                                rut_hash=r_hash,
                                carr_nombre=carr_val or "Sin carrera catalogada",
                                facultad=fac_val or "Sin facultad",
                                anho_ingreso=anho_num,
                                estamento="Estudiante",
                            )
                        )

                    if items_lote:
                        db.add_all(items_lote)
                        await db.commit()
                        total_insertados += len(items_lote)
                        job.registros_ok = total_insertados
                        await db.commit()
                    del items_lote

                else:
                    # Ingesta custom o genérica
                    total_insertados += len(chunk_df)
                    job.registros_ok = total_insertados
                    await db.commit()

                # Liberación forzosa de memoria del lote
                del chunk_df
                gc.collect()

            # Finalización exitosa
            job.estado = "completed"
            job.completado_en = datetime.now(timezone.utc)
            await db.commit()
            logger.info(f"[ingesta] Job {job_id} completado con éxito: {total_insertados} registros.")

            # Invalidación de cachés y actualización de predicciones
            await invalidar_caches_recinto_y_actualizar_predicciones(espacio_id)

        except Exception as exc:
            logger.error(f"[ingesta] Error procesando job {job_id}: {exc}\n{traceback.format_exc()}")
            job.estado = "failed"
            job.error_detail = str(exc)
            job.completado_en = datetime.now(timezone.utc)
            await db.commit()


async def encolar_y_procesar_ingesta(
    job_id: uuid.UUID,
    ruta_archivo: str,
    tipo: str,
    espacio_id: int,
    modo_solapamiento: str = "merge",
    clave_enlace: str = "rut",
    modo_enlace: str = "tolerante",
) -> None:
    """
    Ejecuta el pipeline bajo un semáforo concurrente limitador a 1 ingesta simultánea.
    Las ingestas entrantes concurrentes permanecen en estado 'queued' hasta su turno.
    """
    async with _semaforo_ingesta:
        try:
            await procesar_archivo_por_lotes(
                job_id=job_id,
                ruta_archivo=Path(ruta_archivo),
                tipo=tipo,
                espacio_id=espacio_id,
                modo_solapamiento=modo_solapamiento,
                clave_enlace=clave_enlace,
                modo_enlace=modo_enlace,
            )
        finally:
            # Ley 21.719: se elimina el archivo fuente; el IngestionJob queda como historial
            try:
                Path(ruta_archivo).unlink(missing_ok=True)
                logger.info(f"[ingesta] Archivo fuente del job {job_id} eliminado del volumen.")
            except OSError as exc_borrado:
                logger.error(f"[ingesta] No se pudo eliminar el archivo del job {job_id}: {exc_borrado}")


async def run_ingestion_pipeline(
    job_id: uuid.UUID,
    tipo: str,
    espacio_id: int,
    file_bytes: Optional[bytes] = None,
    filename: Optional[str] = None,
    modo_solapamiento: str = "merge",
    clave_enlace: str = "rut",
    modo_enlace: str = "tolerante",
    ruta_archivo: Optional[str] = None,
):
    """Adaptador de compatibilidad para ejecución asíncrona de pipeline."""
    if not ruta_archivo and file_bytes and filename:
        from app.core.config import settings
        dir_ingesta = Path(settings.DIRECTORIO_INGESTA)
        dir_ingesta.mkdir(parents=True, exist_ok=True)
        dest = dir_ingesta / f"{job_id}_{filename}"
        dest.write_bytes(file_bytes)
        ruta_archivo = str(dest)

    if ruta_archivo:
        await encolar_y_procesar_ingesta(
            job_id=job_id,
            ruta_archivo=ruta_archivo,
            tipo=tipo,
            espacio_id=espacio_id,
            modo_solapamiento=modo_solapamiento,
            clave_enlace=clave_enlace,
            modo_enlace=modo_enlace,
        )


# ---------------------------------------------------------------------------
# Alias para retrocompatibilidad
# ---------------------------------------------------------------------------
compute_file_hash = calcular_hash_archivo
detect_linkage_key = detectar_clave_enlace
extract_file_dataframe = extraer_dataframe_archivo
extract_date_range = extraer_rango_fechas
validate_ingestion_file = validar_archivo_ingesta
execute_atomic_ingestion = ejecutar_ingesta_atomica
_df_to_attendance_dtos = _mapear_df_a_dtos_asistencia


