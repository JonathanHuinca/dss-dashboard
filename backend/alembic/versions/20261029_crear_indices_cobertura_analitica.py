"""crear_indices_cobertura_analitica

Revision ID: b9c8d7e6f5a4
Revises: a1b2c3d4e5f6
Create Date: 2026-10-29 16:25:00.000000-03:00

"""
from alembic import op

# Identificadores de revisión utilizados por Alembic
revision = "b9c8d7e6f5a4"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'IX_ea_cobertura_analitica'
          AND object_id = OBJECT_ID('dbo.eventos_asistencia')
    )
    BEGIN
        CREATE NONCLUSTERED INDEX IX_ea_cobertura_analitica
        ON dbo.eventos_asistencia (espacio_id, time, alerta_coherencia_fechas)
        INCLUDE (person_id_hash, door_entrada, door_salida, salida_imputada, permanencia_min, marcajes_totales, carrera, facultad);
    END
    """)

    op.execute("""
    IF NOT EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'IX_ev_cobertura_analitica'
          AND object_id = OBJECT_ID('dbo.eventos_vehiculares')
    )
    BEGIN
        CREATE NONCLUSTERED INDEX IX_ev_cobertura_analitica
        ON dbo.eventos_vehiculares (espacio_id, time, direccion, calidad_lectura)
        INCLUDE (patente_hash, camara, tipo_vehiculo, marca);
    END
    """)


def downgrade() -> None:
    op.execute("""
    IF EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'IX_ea_cobertura_analitica'
          AND object_id = OBJECT_ID('dbo.eventos_asistencia')
    )
    BEGIN
        DROP INDEX IX_ea_cobertura_analitica ON dbo.eventos_asistencia;
    END
    """)

    op.execute("""
    IF EXISTS (
        SELECT 1
        FROM sys.indexes
        WHERE name = 'IX_ev_cobertura_analitica'
          AND object_id = OBJECT_ID('dbo.eventos_vehiculares')
    )
    BEGIN
        DROP INDEX IX_ev_cobertura_analitica ON dbo.eventos_vehiculares;
    END
    """)

