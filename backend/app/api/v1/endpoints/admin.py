from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.api.v1.endpoints.auth import require_role
from app.core.database import get_db
from app.domain.auth_models import Usuario
from app.domain.chat_audit_models import ChatAuditLog

router = APIRouter()


class ChatAuditItem(BaseModel):
    id: int
    usuario_id: Optional[int] = None
    usuario_email: Optional[str] = None
    usuario_nombre: Optional[str] = None
    prompt_text: str
    dataset_tipo: Optional[str] = None
    modelo_utilizado: Optional[str] = None
    status: str
    response_time_ms: Optional[float] = None
    timestamp: datetime


class HourlyStat(BaseModel):
    hora: str
    cantidad: int


class ChatAuditStats(BaseModel):
    consultas_hoy: int
    consultas_exitosas_hoy: int
    consultas_error_hoy: int
    promedio_tiempo_hoy_ms: float
    consultas_por_dataset_hoy: Dict[str, int]
    consultas_por_hora_hoy: List[HourlyStat]


class ChatAuditResponse(BaseModel):
    items: List[ChatAuditItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    stats: ChatAuditStats


@router.get("/chat-audit", response_model=ChatAuditResponse)
async def get_chat_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(15, ge=1, le=100),
    dataset_tipo: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: Usuario = Depends(require_role("SuperAdmin")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ChatAuditLog)
        .options(joinedload(ChatAuditLog.usuario))
        .order_by(ChatAuditLog.timestamp.desc())
    )
    count_stmt = select(func.count(ChatAuditLog.id))

    if dataset_tipo:
        stmt = stmt.where(ChatAuditLog.dataset_tipo == dataset_tipo)
        count_stmt = count_stmt.where(ChatAuditLog.dataset_tipo == dataset_tipo)
    if status_filter:
        stmt = stmt.where(ChatAuditLog.status == status_filter)
        count_stmt = count_stmt.where(ChatAuditLog.status == status_filter)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(ChatAuditLog.prompt_text.ilike(search_pattern))
        count_stmt = count_stmt.where(ChatAuditLog.prompt_text.ilike(search_pattern))

    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, (total + page_size - 1) // page_size)

    paginated_stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(paginated_stmt)).scalars().all()

    items = [
        ChatAuditItem(
            id=r.id,
            usuario_id=r.usuario_id,
            usuario_email=r.usuario.email if r.usuario else None,
            usuario_nombre=r.usuario.nombre_completo if r.usuario else None,
            prompt_text=r.prompt_text,
            dataset_tipo=r.dataset_tipo,
            modelo_utilizado=r.modelo_utilizado,
            status=r.status,
            response_time_ms=r.response_time_ms,
            timestamp=r.timestamp,
        )
        for r in rows
    ]

    now_utc = datetime.now(timezone.utc)
    today_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

    today_stmt = select(ChatAuditLog).where(ChatAuditLog.timestamp >= today_start)
    today_rows = (await db.execute(today_stmt)).scalars().all()

    consultas_hoy = len(today_rows)
    consultas_exitosas_hoy = sum(1 for r in today_rows if r.status == "éxito")
    consultas_error_hoy = sum(1 for r in today_rows if r.status == "error")

    times = [r.response_time_ms for r in today_rows if r.response_time_ms is not None]
    promedio_tiempo_hoy_ms = round(sum(times) / len(times), 2) if times else 0.0

    datasets_count: Dict[str, int] = {}
    for r in today_rows:
        ds = r.dataset_tipo or "general"
        datasets_count[ds] = datasets_count.get(ds, 0) + 1

    hours_map = {f"{h:02d}:00": 0 for h in range(8, 22)}
    for r in today_rows:
        h_str = f"{r.timestamp.hour:02d}:00"
        if h_str in hours_map:
            hours_map[h_str] += 1
        else:
            hours_map[h_str] = 1

    consultas_por_hora_hoy = [
        HourlyStat(hora=h, cantidad=c) for h, c in sorted(hours_map.items())
    ]

    return ChatAuditResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        stats=ChatAuditStats(
            consultas_hoy=consultas_hoy,
            consultas_exitosas_hoy=consultas_exitosas_hoy,
            consultas_error_hoy=consultas_error_hoy,
            promedio_tiempo_hoy_ms=promedio_tiempo_hoy_ms,
            consultas_por_dataset_hoy=datasets_count,
            consultas_por_hora_hoy=consultas_por_hora_hoy,
        ),
    )
