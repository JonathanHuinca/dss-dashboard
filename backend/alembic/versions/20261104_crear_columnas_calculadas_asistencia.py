"""crear_columnas_calculadas_asistencia

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-11-04 21:30:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columna calculada hora_dia (0 a 23)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns 
            WHERE object_id = OBJECT_ID('eventos_asistencia') 
              AND name = 'hora_dia'
        )
        BEGIN
            ALTER TABLE eventos_asistencia 
            ADD hora_dia AS (DATEPART(hour, time));
        END
    """)

    # 2. Columna calculada dia_semana_iso (1=Lunes .. 7=Domingo)
    # Expresion determinista que independiza la consulta de @@DATEFIRST
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.columns 
            WHERE object_id = OBJECT_ID('eventos_asistencia') 
              AND name = 'dia_semana_iso'
        )
        BEGIN
            ALTER TABLE eventos_asistencia 
            ADD dia_semana_iso AS (((DATEDIFF(day, 0, time) % 7) + 1));
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.columns 
            WHERE object_id = OBJECT_ID('eventos_asistencia') 
              AND name = 'dia_semana_iso'
        )
        BEGIN
            ALTER TABLE eventos_asistencia DROP COLUMN dia_semana_iso;
        END
    """)

    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.columns 
            WHERE object_id = OBJECT_ID('eventos_asistencia') 
              AND name = 'hora_dia'
        )
        BEGIN
            ALTER TABLE eventos_asistencia DROP COLUMN hora_dia;
        END
    """)

