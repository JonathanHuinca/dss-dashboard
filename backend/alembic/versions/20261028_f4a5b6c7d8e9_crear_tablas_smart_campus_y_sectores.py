"""crear_tablas_smart_campus_y_sectores

Revision ID: f4a5b6c7d8e9
Revises: 088d27852340
Create Date: 2026-10-28 22:15:00.000000-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = 'f4a5b6c7d8e9'
down_revision = '088d27852340'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Crear tabla estado_sincronizacion_fuente
    op.create_table(
        'estado_sincronizacion_fuente',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fuente', sa.String(length=40), nullable=False),
        sa.Column('espacio_id', sa.Integer(), nullable=False),
        sa.Column('ultima_fecha_sincronizada', sa.Date(), nullable=True),
        sa.Column('ultima_ejecucion_en', mssql.DATETIME2(), nullable=True),
        sa.Column('filas_leidas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('filas_insertadas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('filas_duplicadas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='exitoso'),
        sa.Column('ultimo_error', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['espacio_id'], ['espacios.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_esf_fuente_espacio', 'estado_sincronizacion_fuente', ['fuente', 'espacio_id'])

    # 2. Crear tabla sectores_estacionamiento
    op.create_table(
        'sectores_estacionamiento',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('espacio_id', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('codigo', sa.String(length=20), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('capacidad_max', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('camaras_entrada', sa.String(length=255), nullable=True),
        sa.Column('camaras_salida', sa.String(length=255), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default='1'),
        sa.ForeignKeyConstraint(['espacio_id'], ['espacios.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo', name='uq_sectores_estacionamiento_codigo')
    )
    op.create_index('ix_se_espacio_id', 'sectores_estacionamiento', ['espacio_id'])

    # 3. Sembrar los 3 sectores de estacionamiento institucionales
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM espacios WHERE id = 2)
    BEGIN
        SET IDENTITY_INSERT espacios ON;
        INSERT INTO espacios (id, campus, tipo, nombre, capacidad_max, activo) 
        VALUES (2, 'San Francisco', 'estacionamiento', 'Estacionamiento Campus San Francisco', 270, 1);
        SET IDENTITY_INSERT espacios OFF;
    END

    IF NOT EXISTS (SELECT 1 FROM sectores_estacionamiento WHERE codigo = 'CSF11')
    BEGIN
        INSERT INTO sectores_estacionamiento (espacio_id, codigo, nombre, capacidad_max, camaras_entrada, camaras_salida, activo)
        VALUES (2, 'CSF11', 'Edificio 11 (Campus San Francisco)', 120, 'CSF11 ANPR 01', 'CSF11 ANPR 02', 1);
    END

    IF NOT EXISTS (SELECT 1 FROM sectores_estacionamiento WHERE codigo = 'CSF21')
    BEGIN
        INSERT INTO sectores_estacionamiento (espacio_id, codigo, nombre, capacidad_max, camaras_entrada, camaras_salida, activo)
        VALUES (2, 'CSF21', 'Edificio 21 (Campus San Francisco)', 100, 'CSF21 ANPR 01', 'CSF21 ANPR 02', 1);
    END

    IF NOT EXISTS (SELECT 1 FROM sectores_estacionamiento WHERE codigo = 'CHS01')
    BEGIN
        INSERT INTO sectores_estacionamiento (espacio_id, codigo, nombre, capacidad_max, camaras_entrada, camaras_salida, activo)
        VALUES (2, 'CHS01', 'Hospital de Simulación (CHS)', 50, 'CHS01_00 ANPR 01', 'CHS01_00 ANPR 02', 1);
    END
    """)


def downgrade() -> None:
    op.drop_table('sectores_estacionamiento')
    op.drop_table('estado_sincronizacion_fuente')

