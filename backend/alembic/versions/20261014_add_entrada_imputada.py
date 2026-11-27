"""Add entrada_imputada and make primera_entrada nullable

Revision ID: e4b3c2d1a098
Revises: a7f8e91d2c3b
Create Date: 2026-10-14 17:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'e4b3c2d1a098'
down_revision = 'a7f8e91d2c3b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Permitir nulos en primera_entrada
    op.alter_column('eventos_asistencia', 'primera_entrada', existing_type=mssql.DATETIME2(), nullable=True)
    # 2. Agregar bandera entrada_imputada
    op.add_column('eventos_asistencia', sa.Column('entrada_imputada', sa.Boolean(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.execute("""
        DECLARE @df NVARCHAR(200);
        SELECT @df = dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
        WHERE dc.parent_object_id = OBJECT_ID('dbo.eventos_asistencia') AND c.name = 'entrada_imputada';
        IF @df IS NOT NULL
            EXEC('ALTER TABLE dbo.eventos_asistencia DROP CONSTRAINT [' + @df + ']');
    """)
    op.drop_column('eventos_asistencia', 'entrada_imputada')
    op.execute("UPDATE dbo.eventos_asistencia SET primera_entrada = time WHERE primera_entrada IS NULL;")
    op.alter_column('eventos_asistencia', 'primera_entrada', existing_type=mssql.DATETIME2(), nullable=False)
