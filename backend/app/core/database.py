from typing import Any, AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Inicializa de forma diferida el motor SQLAlchemy asíncrono para evitar fallo si falta aioodbc al importar."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            fast_executemany=True,
            echo=False,
            pool_size=15,
            max_overflow=20,
            pool_timeout=15,
            pool_recycle=1800,
            pool_pre_ping=True,
            connect_args={"timeout": 15},
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Retorna la fábrica singleton de sesiones asíncronas."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


class _LazyEngineProxy:
    """Proxy diferido para mantener compatibilidad con `from app.core.database import engine`."""

    async def dispose(self) -> None:
        global _engine, _session_factory
        if _engine is not None:
            await _engine.dispose()
            _engine = None
            _session_factory = None

    def __getattr__(self, item: str) -> Any:
        return getattr(get_engine(), item)


class _LazySessionFactoryProxy:
    """Proxy diferido invocable compatible con `async with AsyncSessionLocal() as db:` y `patch.object`."""

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return get_session_factory()(*args, **kwargs)

    def __getattr__(self, item: str) -> Any:
        return getattr(get_session_factory(), item)


engine: Any = _LazyEngineProxy()
AsyncSessionLocal: Any = _LazySessionFactoryProxy()


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
