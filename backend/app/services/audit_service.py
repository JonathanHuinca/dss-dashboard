import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from sqlalchemy import case, func, select
from sqlalchemy.orm import contains_eager, joinedload

from app.core.database import AsyncSessionLocal
from app.core.tiempo import inicio_dia_chile
from app.domain.download_audit_models import DownloadAuditLog
from app.domain.auth_models import Usuario

logger = logging.getLogger(__name__)


async def record_download_audit(
    usuario_id: Optional[int],
    modulo: str,
    formato: str,
    filtro_fecha_inicio: Optional[str] = None,
    filtro_fecha_fin: Optional[str] = None,
    filtro_detalle: Optional[str] = None,
    total_registros: int = 0,
    ip_origen: Optional[str] = None,
) -> None:
    """Registra de forma segura un evento de descarga en download_audit_logs."""
    try:
        async with AsyncSessionLocal() as session:
            audit = DownloadAuditLog(
                usuario_id=usuario_id,
                modulo=modulo,
                formato=formato.lower(),
                filtro_fecha_inicio=str(filtro_fecha_inicio) if filtro_fecha_inicio else None,
                filtro_fecha_fin=str(filtro_fecha_fin) if filtro_fecha_fin else None,
                filtro_detalle=filtro_detalle,
                total_registros=total_registros,
                ip_origen=ip_origen,
            )
            session.add(audit)
            await session.commit()
    except Exception as e:
        logger.warning(f"No se pudo registrar la auditoría de descarga: {e}")


async def get_download_audit_history(
    page: int = 1,
    page_size: int = 20,
    modulo: Optional[str] = None,
    formato: Optional[str] = None,
    search: Optional[str] = None,
) -> Dict[str, Any]:
    """Obtiene el historial de descargas paginado con estadísticas para el Administrador."""
    async with AsyncSessionLocal() as session:
        stmt = (
            select(DownloadAuditLog)
            .order_by(DownloadAuditLog.timestamp.desc())
        )
        count_stmt = select(func.count(DownloadAuditLog.id))

        if modulo:
            stmt = stmt.where(DownloadAuditLog.modulo == modulo)
            count_stmt = count_stmt.where(DownloadAuditLog.modulo == modulo)
        if formato:
            stmt = stmt.where(DownloadAuditLog.formato == formato.lower())
            count_stmt = count_stmt.where(DownloadAuditLog.formato == formato.lower())
        if search:
            search_pattern = f"%{search}%"
            stmt = (
                stmt.outerjoin(Usuario, DownloadAuditLog.usuario_id == Usuario.id)
                .options(contains_eager(DownloadAuditLog.usuario))
                .where(
                    (DownloadAuditLog.filtro_detalle.ilike(search_pattern))
                    | (Usuario.email.ilike(search_pattern))
                    | (Usuario.nombre_completo.ilike(search_pattern))
                )
            )
            count_stmt = count_stmt.outerjoin(Usuario, DownloadAuditLog.usuario_id == Usuario.id).where(
                (DownloadAuditLog.filtro_detalle.ilike(search_pattern))
                | (Usuario.email.ilike(search_pattern))
                | (Usuario.nombre_completo.ilike(search_pattern))
            )
        else:
            stmt = stmt.options(joinedload(DownloadAuditLog.usuario))

        total = (await session.execute(count_stmt)).scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        offset = max(0, (page - 1) * page_size)

        paginated_stmt = stmt.offset(offset).limit(page_size)
        rows = (await session.execute(paginated_stmt)).scalars().all()

        items = [
            {
                "id": r.id,
                "usuario_id": r.usuario_id,
                "usuario_email": r.usuario.email if r.usuario else "Anónimo / Sistema",
                "usuario_nombre": r.usuario.nombre_completo if r.usuario else "Operador",
                "modulo": r.modulo,
                "formato": r.formato,
                "filtro_fecha_inicio": r.filtro_fecha_inicio,
                "filtro_fecha_fin": r.filtro_fecha_fin,
                "filtro_detalle": r.filtro_detalle,
                "total_registros": r.total_registros,
                "ip_origen": r.ip_origen or "127.0.0.1",
                "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S") if r.timestamp else None,
            }
            for r in rows
        ]

        # Estadísticas acumuladas calculadas en SQL sin cargar toda la tabla a RAM
        today_start_cl = inicio_dia_chile().replace(tzinfo=None)

        stats_stmt = select(
            func.count(DownloadAuditLog.id),
            func.sum(case((DownloadAuditLog.timestamp >= today_start_cl, 1), else_=0)),
            func.sum(case((DownloadAuditLog.formato == "csv", 1), else_=0)),
            func.sum(case((DownloadAuditLog.formato == "pdf", 1), else_=0)),
        )
        agg = (await session.execute(stats_stmt)).one()
        total_descargas = int(agg[0] or 0)
        descargas_hoy = int(agg[1] or 0)
        descargas_csv = int(agg[2] or 0)
        descargas_pdf = int(agg[3] or 0)

        modulos_stmt = select(DownloadAuditLog.modulo, func.count(DownloadAuditLog.id)).group_by(DownloadAuditLog.modulo)
        modulos_rows = (await session.execute(modulos_stmt)).all()
        modulos_count: Dict[str, int] = {str(m): int(c) for m, c in modulos_rows if m is not None}

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "stats": {
                "total_descargas": total_descargas,
                "descargas_hoy": descargas_hoy,
                "descargas_csv": descargas_csv,
                "descargas_pdf": descargas_pdf,
                "descargas_por_modulo": modulos_count,
            },
        }
