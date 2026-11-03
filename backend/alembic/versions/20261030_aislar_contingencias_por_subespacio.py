"""aislar_contingencias_por_subespacio

Revision ID: c0d1e2f3a4b5
Revises: b9c8d7e6f5a4
Create Date: 2026-10-30 11:20:00.000000-03:00

"""
from alembic import op

# Identificadores de revisión utilizados por Alembic
revision = "c0d1e2f3a4b5"
down_revision = "b9c8d7e6f5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    IF COL_LENGTH('dbo.contingencias_academicas', 'espacio_id') IS NULL
        ALTER TABLE dbo.contingencias_academicas ADD espacio_id INT NULL;
    IF COL_LENGTH('dbo.contingencias_academicas', 'subespacio') IS NULL
        ALTER TABLE dbo.contingencias_academicas ADD subespacio VARCHAR(50) NULL DEFAULT 'todos';
    IF COL_LENGTH('dbo.contingencias_academicas', 'hora_inicio') IS NULL
        ALTER TABLE dbo.contingencias_academicas ADD hora_inicio VARCHAR(5) NULL;
    IF COL_LENGTH('dbo.contingencias_academicas', 'hora_fin') IS NULL
        ALTER TABLE dbo.contingencias_academicas ADD hora_fin VARCHAR(5) NULL;
    """)


def downgrade() -> None:
    op.execute("""
    IF COL_LENGTH('dbo.contingencias_academicas', 'hora_fin') IS NOT NULL
        ALTER TABLE dbo.contingencias_academicas DROP COLUMN hora_fin;
    IF COL_LENGTH('dbo.contingencias_academicas', 'hora_inicio') IS NOT NULL
        ALTER TABLE dbo.contingencias_academicas DROP COLUMN hora_inicio;
    IF COL_LENGTH('dbo.contingencias_academicas', 'subespacio') IS NOT NULL
        ALTER TABLE dbo.contingencias_academicas DROP COLUMN subespacio;
    IF COL_LENGTH('dbo.contingencias_academicas', 'espacio_id') IS NOT NULL
        ALTER TABLE dbo.contingencias_academicas DROP COLUMN espacio_id;
    """)

