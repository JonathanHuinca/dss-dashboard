"""crear_tabla_estado_calendario_anual

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-27 12:40:00.000000-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'estado_calendario_anual',
        sa.Column('anio_objetivo', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='pendiente'),
        sa.Column('intentos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultimo_intento_en', mssql.DATETIME2(), nullable=True),
        sa.Column('proximo_intento_en', mssql.DATETIME2(), nullable=True),
        sa.Column('ultimo_error', sa.Text(), nullable=True),
        sa.Column('eventos_encontrados', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('anio_objetivo'),
        sa.CheckConstraint("estado IN ('pendiente', 'completo')", name='ck_estado_calendario_anual_estado')
    )


def downgrade() -> None:
    op.drop_table('estado_calendario_anual')
