"""crear_tabla_ejecuciones_tareas

Revision ID: d2e3f4a5b6c7
Revises: c1a2b3c4d5e6
Create Date: 2026-10-27 11:30:00.000000-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'd2e3f4a5b6c7'
down_revision = 'c1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ejecuciones_tareas',
        sa.Column('id', mssql.UNIQUEIDENTIFIER(), nullable=False),
        sa.Column('tarea', sa.String(length=100), nullable=False),
        sa.Column('disparador', sa.String(length=20), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('inicio_en', mssql.DATETIME2(), nullable=False),
        sa.Column('fin_en', mssql.DATETIME2(), nullable=True),
        sa.Column('latido_en', mssql.DATETIME2(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('resumen_json', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('memoria_pico_mb', sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("disparador IN ('programado', 'manual', 'recuperacion')", name='ck_ejecuciones_tareas_disparador'),
        sa.CheckConstraint("estado IN ('en_curso', 'exitoso', 'fallido', 'omitido')", name='ck_ejecuciones_tareas_estado')
    )
    op.create_index(
        'ix_ejecuciones_tareas_tarea_inicio',
        'ejecuciones_tareas',
        ['tarea', 'inicio_en'],
        unique=False
    )
    op.create_index(
        'ix_ejecuciones_tareas_tarea',
        'ejecuciones_tareas',
        ['tarea'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_ejecuciones_tareas_tarea', table_name='ejecuciones_tareas')
    op.drop_index('ix_ejecuciones_tareas_tarea_inicio', table_name='ejecuciones_tareas')
    op.drop_table('ejecuciones_tareas')
