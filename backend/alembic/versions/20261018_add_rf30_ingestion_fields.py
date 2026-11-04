"""Add RF30 ingestion fields and curricular dimensions

Revision ID: b2c3d4e5f601
Revises: e4b3c2d1a098
Create Date: 2026-10-18 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f601'
down_revision = 'e4b3c2d1a098'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Campos de carrera en eventos_asistencia
    op.add_column('eventos_asistencia', sa.Column('carrera', sa.String(length=150), nullable=True))
    op.add_column('eventos_asistencia', sa.Column('facultad', sa.String(length=150), nullable=True))
    op.add_column('eventos_asistencia', sa.Column('estamento', sa.String(length=50), nullable=True))

    # 2. Campos de control criptografico y colisiones en ingestion_jobs
    op.add_column('ingestion_jobs', sa.Column('file_hash', sa.String(length=64), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('fecha_min', mssql.DATETIME2(), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('fecha_max', mssql.DATETIME2(), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('modo_solapamiento', sa.String(length=20), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('clave_enlace', sa.String(length=20), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('modo_enlace', sa.String(length=20), nullable=True))
    op.add_column('ingestion_jobs', sa.Column('espacio_id', sa.Integer(), nullable=True))
    op.create_index('ix_ij_file_hash', 'ingestion_jobs', ['file_hash'])

    # 3. Tabla dim_carrera_programa
    op.create_table(
        'dim_carrera_programa',
        sa.Column('carr_codigo', sa.String(length=20), primary_key=True),
        sa.Column('carr_nombre', sa.String(length=150), nullable=False),
        sa.Column('facultad', sa.String(length=150), nullable=True),
    )

    # 4. Tabla dim_estudiante_carrera
    op.create_table(
        'dim_estudiante_carrera',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('person_id_hash', sa.String(length=64), nullable=False),
        sa.Column('matricula', sa.String(length=50), nullable=True),
        sa.Column('rut_hash', sa.String(length=64), nullable=True),
        sa.Column('carr_codigo', sa.String(length=20), nullable=True),
        sa.Column('carr_nombre', sa.String(length=150), nullable=True),
        sa.Column('facultad', sa.String(length=150), nullable=True),
        sa.Column('anho_ingreso', sa.SmallInteger(), nullable=True),
        sa.Column('estamento', sa.String(length=50), server_default='Estudiante', nullable=True),
    )
    op.create_index('ix_dec_person_id', 'dim_estudiante_carrera', ['person_id_hash'])
    op.create_index('ix_dec_matricula', 'dim_estudiante_carrera', ['matricula'])
    op.create_index('ix_dec_rut_hash', 'dim_estudiante_carrera', ['rut_hash'])


def downgrade() -> None:
    op.drop_table('dim_estudiante_carrera')
    op.drop_table('dim_carrera_programa')
    op.drop_index('ix_ij_file_hash', 'ingestion_jobs')
    op.drop_column('ingestion_jobs', 'espacio_id')
    op.drop_column('ingestion_jobs', 'modo_enlace')
    op.drop_column('ingestion_jobs', 'clave_enlace')
    op.drop_column('ingestion_jobs', 'modo_solapamiento')
    op.drop_column('ingestion_jobs', 'fecha_max')
    op.drop_column('ingestion_jobs', 'fecha_min')
    op.drop_column('ingestion_jobs', 'file_hash')
    op.drop_column('eventos_asistencia', 'estamento')
    op.drop_column('eventos_asistencia', 'facultad')
    op.drop_column('eventos_asistencia', 'carrera')
