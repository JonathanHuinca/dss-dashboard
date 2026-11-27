"""indices_cubrientes_dashboard

Revision ID: d9e8f7a6b5c4
Revises: c8d9e0f1a2b3
Create Date: 2026-11-09 15:30:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, None] = "c8d9e0f1a2b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_dec_person_covering'
              AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera')
        )
        BEGIN
            CREATE NONCLUSTERED INDEX ix_dec_person_covering
            ON dbo.dim_estudiante_carrera (person_id_hash)
            INCLUDE (carr_nombre, facultad, anho_ingreso);
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_rhd_espacio_fecha_covering'
              AND object_id = OBJECT_ID('dbo.rollup_historico_diario')
        )
        BEGIN
            CREATE NONCLUSTERED INDEX ix_rhd_espacio_fecha_covering
            ON dbo.rollup_historico_diario (espacio_id, fecha, tipo)
            INCLUDE (ingresos_total, salidas_total, personas_unicas, permanencia_mediana_min);
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_ea_espacio_time_covering'
              AND object_id = OBJECT_ID('dbo.eventos_asistencia')
        )
        BEGIN
            CREATE NONCLUSTERED INDEX ix_ea_espacio_time_covering
            ON dbo.eventos_asistencia (espacio_id, time)
            INCLUDE (person_id_hash, permanencia_min, marcajes_totales, alerta_coherencia_fechas, door_entrada, door_salida, carrera, facultad, primera_entrada, ultima_salida, salida_imputada);
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_ev_espacio_time_covering'
              AND object_id = OBJECT_ID('dbo.eventos_vehiculares')
        )
        BEGIN
            CREATE NONCLUSTERED INDEX ix_ev_espacio_time_covering
            ON dbo.eventos_vehiculares (espacio_id, time)
            INCLUDE (patente_hash, direccion, camara, calidad_lectura, tipo_vehiculo);
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_ev_espacio_time_covering'
              AND object_id = OBJECT_ID('dbo.eventos_vehiculares')
        )
        BEGIN
            DROP INDEX ix_ev_espacio_time_covering ON dbo.eventos_vehiculares;
        END
    """)

    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_ea_espacio_time_covering'
              AND object_id = OBJECT_ID('dbo.eventos_asistencia')
        )
        BEGIN
            DROP INDEX ix_ea_espacio_time_covering ON dbo.eventos_asistencia;
        END
    """)

    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_rhd_espacio_fecha_covering'
              AND object_id = OBJECT_ID('dbo.rollup_historico_diario')
        )
        BEGIN
            DROP INDEX ix_rhd_espacio_fecha_covering ON dbo.rollup_historico_diario;
        END
    """)

    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_dec_person_covering'
              AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera')
        )
        BEGIN
            DROP INDEX ix_dec_person_covering ON dbo.dim_estudiante_carrera;
        END
    """)
