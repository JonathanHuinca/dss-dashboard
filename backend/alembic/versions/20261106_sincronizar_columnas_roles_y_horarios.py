"""sincronizar_columnas_roles_y_horarios

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-06 15:50:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF COL_LENGTH('dbo.roles', 'cooldown_segundos') IS NULL
        BEGIN
            ALTER TABLE dbo.roles ADD cooldown_segundos INT NOT NULL CONSTRAINT DF_roles_cooldown_segundos DEFAULT 10;
        END
    """)
    op.execute("""
        IF COL_LENGTH('dbo.horarios_operacion', 'subespacio') IS NULL
        BEGIN
            ALTER TABLE dbo.horarios_operacion ADD subespacio VARCHAR(50) NULL;
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF COL_LENGTH('dbo.horarios_operacion', 'subespacio') IS NOT NULL
        BEGIN
            DECLARE @df_sub NVARCHAR(256);
            SELECT @df_sub = dc.name
            FROM sys.default_constraints dc
            JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
            WHERE dc.parent_object_id = OBJECT_ID('dbo.horarios_operacion') AND c.name = 'subespacio';
            IF @df_sub IS NOT NULL
                EXEC('ALTER TABLE dbo.horarios_operacion DROP CONSTRAINT [' + @df_sub + ']');
            ALTER TABLE dbo.horarios_operacion DROP COLUMN subespacio;
        END
    """)
    op.execute("""
        IF COL_LENGTH('dbo.roles', 'cooldown_segundos') IS NOT NULL
        BEGIN
            DECLARE @df NVARCHAR(256);
            SELECT @df = dc.name
            FROM sys.default_constraints dc
            JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
            WHERE dc.parent_object_id = OBJECT_ID('dbo.roles') AND c.name = 'cooldown_segundos';
            IF @df IS NOT NULL
                EXEC('ALTER TABLE dbo.roles DROP CONSTRAINT [' + @df + ']');
            ALTER TABLE dbo.roles DROP COLUMN cooldown_segundos;
        END
    """)
