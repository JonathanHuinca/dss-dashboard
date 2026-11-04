"""crear_vistas_indexadas_rendimiento

Revision ID: a1b2c3d4e5f6
Revises: f4a5b6c7d8e9
Create Date: 2026-10-28 22:30:00.000000-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Vista Indexada: vehiculos_diario_estacionamiento
    op.execute("""
    IF OBJECT_ID('dbo.vehiculos_diario_estacionamiento', 'V') IS NOT NULL
        DROP VIEW dbo.vehiculos_diario_estacionamiento;
    """)
    op.execute("""
    CREATE VIEW dbo.vehiculos_diario_estacionamiento WITH SCHEMABINDING AS
    SELECT 
        espacio_id,
        camara,
        direccion,
        DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) AS fecha_dia,
        COUNT_BIG(*) AS total_eventos
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, camara, direccion, DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126));
    """)
    op.execute("""
    CREATE UNIQUE CLUSTERED INDEX UQ_vehiculos_diario_estacionamiento 
    ON dbo.vehiculos_diario_estacionamiento (fecha_dia, espacio_id, camara, direccion);
    """)

    # 2. Vista Indexada: asistencia_diaria_biblioteca
    op.execute("""
    IF OBJECT_ID('dbo.asistencia_diaria_biblioteca', 'V') IS NOT NULL
        DROP VIEW dbo.asistencia_diaria_biblioteca;
    """)
    op.execute("""
    CREATE VIEW dbo.asistencia_diaria_biblioteca WITH SCHEMABINDING AS
    SELECT 
        espacio_id,
        salida_imputada AS es_salida,
        ISNULL(door_entrada, ISNULL(door_salida, 'Torniquete')) AS puerta,
        DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) AS fecha_dia,
        COUNT_BIG(*) AS total_eventos
    FROM dbo.eventos_asistencia
    GROUP BY espacio_id, salida_imputada, ISNULL(door_entrada, ISNULL(door_salida, 'Torniquete')), DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126));
    """)
    op.execute("""
    CREATE UNIQUE CLUSTERED INDEX UQ_asistencia_diaria_biblioteca 
    ON dbo.asistencia_diaria_biblioteca (fecha_dia, espacio_id, puerta, es_salida);
    """)

    # 3. Vista Indexada: vehiculos_composicion_flota
    op.execute("""
    IF OBJECT_ID('dbo.vehiculos_composicion_flota', 'V') IS NOT NULL
        DROP VIEW dbo.vehiculos_composicion_flota;
    """)
    op.execute("""
    CREATE VIEW dbo.vehiculos_composicion_flota WITH SCHEMABINDING AS
    SELECT 
        espacio_id,
        ISNULL(tipo_vehiculo, 'Otros') AS tipo_vehiculo,
        direccion,
        DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126)) AS fecha_dia,
        COUNT_BIG(*) AS total_eventos
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, ISNULL(tipo_vehiculo, 'Otros'), direccion, DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, '2000-01-01T00:00:00', 126), time), CONVERT(DATETIME2, '2000-01-01T00:00:00', 126));
    """)
    op.execute("""
    CREATE UNIQUE CLUSTERED INDEX UQ_vehiculos_composicion_flota 
    ON dbo.vehiculos_composicion_flota (fecha_dia, espacio_id, tipo_vehiculo, direccion);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS UQ_vehiculos_composicion_flota ON dbo.vehiculos_composicion_flota;")
    op.execute("DROP VIEW IF EXISTS dbo.vehiculos_composicion_flota;")
    op.execute("DROP INDEX IF EXISTS UQ_asistencia_diaria_biblioteca ON dbo.asistencia_diaria_biblioteca;")
    op.execute("DROP VIEW IF EXISTS dbo.asistencia_diaria_biblioteca;")
    op.execute("DROP INDEX IF EXISTS UQ_vehiculos_diario_estacionamiento ON dbo.vehiculos_diario_estacionamiento;")
    op.execute("DROP VIEW IF EXISTS dbo.vehiculos_diario_estacionamiento;")

