"""Update ck_ij_tipo constraint to include curricular and custom

Revision ID: e5f6a7b8c904
Revises: d4e5f6a7b803
Create Date: 2026-10-18 12:15:00.000000

"""
from alembic import op

revision = 'e5f6a7b8c904'
down_revision = 'd4e5f6a7b803'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'ck_ij_tipo')
    BEGIN
        ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ij_tipo;
    END
    ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ij_tipo CHECK (tipo IN ('asistencia', 'vehicular', 'academico', 'curricular', 'custom'));
    """)


def downgrade() -> None:
    op.execute("""
    IF EXISTS (SELECT * FROM sys.check_constraints WHERE name = 'ck_ij_tipo')
    BEGIN
        ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ij_tipo;
    END
    ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ij_tipo CHECK (tipo IN ('asistencia', 'vehicular', 'academico'));
    """)
