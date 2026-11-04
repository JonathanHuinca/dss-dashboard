"""Crear tabla salas_biblioteca y sembrar Sala 1 y Sala 2

Revision ID: f6a7b8c9d005
Revises: e5f6a7b8c904
Create Date: 2026-10-18 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d005'
down_revision = 'e5f6a7b8c904'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'salas_biblioteca',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('espacio_id', sa.Integer(), sa.ForeignKey('espacios.id'), nullable=False),
        sa.Column('codigo', sa.String(length=50), nullable=False, unique=True),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('edificio', sa.String(length=50), nullable=False),
        sa.Column('piso', sa.String(length=50), nullable=False),
        sa.Column('descripcion', sa.String(length=255), nullable=True),
        sa.Column('capacidad_asientos', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('permite_horario_extendido', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('puerta_principal_in', sa.String(length=80), nullable=True),
        sa.Column('puerta_principal_out', sa.String(length=80), nullable=True),
        sa.Column('puerta_universal_in', sa.String(length=80), nullable=True),
        sa.Column('puerta_universal_out', sa.String(length=80), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('1')),
    )
    op.create_index('ix_sb_espacio_id', 'salas_biblioteca', ['espacio_id'])

    # Sembrar Sala 1 y Sala 2 institucionales
    op.execute("""
    IF NOT EXISTS (SELECT 1 FROM espacios WHERE id = 1)
    BEGIN
        SET IDENTITY_INSERT espacios ON;
        INSERT INTO espacios (id, campus, tipo, nombre, capacidad_max, activo) 
        VALUES (1, 'San Francisco', 'biblioteca', 'Biblioteca Campus San Francisco', 200, 1);
        SET IDENTITY_INSERT espacios OFF;
    END

    INSERT INTO salas_biblioteca (
        espacio_id, codigo, nombre, edificio, piso, descripcion, capacidad_asientos, 
        permite_horario_extendido, puerta_principal_in, puerta_principal_out, 
        puerta_universal_in, puerta_universal_out, activo
    ) VALUES 
    (
        1, 'SALA_1_CSF02', 'Sala 1 — Estudio y Biblioteca con Locker', 'CSF02', '2do Piso',
        '2do piso, sala de estudio y biblioteca con locker. Acceso 1 torniquete principal y 1 universal.',
        124, 0, 'CSF02_320 CTRA IN 02', 'CSF02_320 CTRA OUT 02',
        'CSF02_320 CTRA IN 01', 'CSF02_320 CTRA OUT 01', 1
    ),
    (
        1, 'SALA_2_CSF04', 'Sala 2 — Pecera de Estudio', 'CSF04', '1er Piso',
        '1er piso, sala pecera de estudio. Capacidad 226 asientos con posibilidad de horario extendido en exámenes.',
        226, 1, 'CSF04_110 IN 01', 'CSF04_110 OUT',
        'CSF04_110 IN 02_Door_1', 'CSF04_110 OUT 02_Door_1', 1
    );
    """)


def downgrade() -> None:
    op.drop_index('ix_sb_espacio_id', table_name='salas_biblioteca')
    op.drop_table('salas_biblioteca')
