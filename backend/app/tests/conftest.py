"""Fixtures compartidos y aislados para las pruebas automatizadas del backend DSS UCT."""
import os
import sys
from datetime import datetime, timezone
from typing import Generator, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.core.database import get_db
from app.core.security import get_current_user
from app.domain.auth_models import Rol, Usuario
from app.main import app


def crear_usuario_mock(
    email: str,
    roles_nombres: List[str],
    espacio_id: Optional[int] = None,
    allowed_datasets: Optional[List[str]] = None,
    can_use_ai: bool = True,
    can_export: bool = True,
    can_ingest: bool = False,
    user_id: int = 100,
) -> Usuario:
    """Construye un modelo Usuario desacoplado de SQL Server para pruebas aisladas."""
    u = Usuario(
        id=user_id,
        email=email,
        nombre_completo=f"Usuario {email}",
        hashed_password="hash_simulado_bcrypt",
        is_active=True,
        espacio_id=espacio_id,
        allowed_datasets=allowed_datasets if allowed_datasets is not None else ["biblioteca", "estacionamiento"],
        can_use_ai=can_use_ai,
        can_export=can_export,
        can_ingest=can_ingest,
        created_at=datetime.now(timezone.utc),
    )
    u.roles = [Rol(id=idx + 1, nombre=nombre) for idx, nombre in enumerate(roles_nombres)]
    return u


def crear_db_mock() -> AsyncMock:
    """Crea una sesión AsyncMock segura con resultados vacíos por defecto."""
    db = AsyncMock()
    res_vacio = MagicMock()
    res_vacio.scalar_one_or_none.return_value = None
    res_vacio.scalar.return_value = None
    res_vacio.scalars.return_value.all.return_value = []
    res_vacio.all.return_value = []
    res_vacio.mappings.return_value.all.return_value = []
    res_vacio.mappings.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=res_vacio)
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.close = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def _limpiar_dependency_overrides() -> Generator[None, None, None]:
    """Garantiza aislamiento entre pruebas limpiando dependency_overrides al finalizar."""
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db() -> AsyncMock:
    return crear_db_mock()


@pytest.fixture
def admin_user() -> Usuario:
    return crear_usuario_mock("admin@uct.cl", ["Admin_Sistema"], can_ingest=True, user_id=1)


@pytest.fixture
def director_bib_user() -> Usuario:
    return crear_usuario_mock(
        "director.bib@uct.cl",
        ["Director_Recinto"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
        can_ingest=True,
        user_id=2,
    )


@pytest.fixture
def director_est_user() -> Usuario:
    return crear_usuario_mock(
        "director.est@uct.cl",
        ["Director_Recinto"],
        espacio_id=2,
        allowed_datasets=["estacionamiento"],
        can_ingest=True,
        user_id=3,
    )


@pytest.fixture
def analista_bib_user() -> Usuario:
    return crear_usuario_mock(
        "analista.bib@uct.cl",
        ["Analista_Consulta"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
        can_ingest=False,
        user_id=4,
    )


@pytest.fixture
def guardia_bib_user() -> Usuario:
    return crear_usuario_mock(
        "guardia.bib@uct.cl",
        ["Guardia_Seguridad"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
        can_use_ai=False,
        can_export=False,
        can_ingest=False,
        user_id=5,
    )


@pytest.fixture
def consultor_user() -> Usuario:
    return crear_usuario_mock(
        "consultor@uct.cl",
        ["Consultor_Reporte"],
        espacio_id=1,
        allowed_datasets=["biblioteca"],
        can_use_ai=False,
        can_export=False,
        can_ingest=False,
        user_id=6,
    )


@pytest.fixture
def app_client(fake_db: AsyncMock):
    """Fábrica de TestClient sin arranque de lifespan productivo."""

    def _crear(usuario: Optional[Usuario] = None, db_override: Optional[AsyncMock] = None) -> TestClient:
        sesion = db_override or fake_db

        async def _fake_get_db():
            yield sesion

        app.dependency_overrides[get_db] = _fake_get_db
        if usuario is not None:
            app.dependency_overrides[get_current_user] = lambda: usuario
        else:
            app.dependency_overrides.pop(get_current_user, None)
        return TestClient(app, raise_server_exceptions=False)

    return _crear
