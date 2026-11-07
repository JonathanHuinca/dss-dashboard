"""actualizar_directivo_multirrecinto

Revision ID: c8d9e0f1a2b3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-07 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE dbo.usuarios
        SET espacio_id = NULL
        WHERE email = 'directivo@uct.cl';
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE dbo.usuarios
        SET espacio_id = 1
        WHERE email = 'directivo@uct.cl';
    """)
