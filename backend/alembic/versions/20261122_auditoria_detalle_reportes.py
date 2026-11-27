"""Agregar detalle y user_agent a auditoria_accesos_reporte

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-11-22 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF COL_LENGTH('auditoria_accesos_reporte', 'detalle') IS NULL
        BEGIN
            ALTER TABLE auditoria_accesos_reporte ADD detalle NVARCHAR(500) NULL;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('auditoria_accesos_reporte', 'user_agent') IS NULL
        BEGIN
            ALTER TABLE auditoria_accesos_reporte ADD user_agent NVARCHAR(255) NULL;
        END
        """
    )
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_auditoria_accesos_reporte_rep_fecha'
              AND object_id = OBJECT_ID('auditoria_accesos_reporte')
        )
        BEGIN
            CREATE INDEX ix_auditoria_accesos_reporte_rep_fecha
            ON auditoria_accesos_reporte (reporte_id, fecha_hora DESC);
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_auditoria_accesos_reporte_rep_fecha'
              AND object_id = OBJECT_ID('auditoria_accesos_reporte')
        )
        BEGIN
            DROP INDEX ix_auditoria_accesos_reporte_rep_fecha ON auditoria_accesos_reporte;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('auditoria_accesos_reporte', 'user_agent') IS NOT NULL
        BEGIN
            ALTER TABLE auditoria_accesos_reporte DROP COLUMN user_agent;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('auditoria_accesos_reporte', 'detalle') IS NOT NULL
        BEGIN
            ALTER TABLE auditoria_accesos_reporte DROP COLUMN detalle;
        END
        """
    )
