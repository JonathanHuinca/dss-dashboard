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
    op.drop_column('eventos_asistencia', 'entrada_imputada')
    op.alter_column('eventos_asistencia', 'primera_entrada', existing_type=mssql.DATETIME2(), nullable=False)
