"""crear_tablas_reportes_compartidos

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-10-30 14:58:00.000000-03:00

"""
from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    IF OBJECT_ID('dbo.destinatarios_reportes', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.destinatarios_reportes (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            email NVARCHAR(150) NOT NULL UNIQUE,
            nombre_completo NVARCHAR(150) NOT NULL,
            cargo NVARCHAR(120) NOT NULL,
            unidad_academica NVARCHAR(180) NOT NULL,
            token_portal VARCHAR(64) NOT NULL UNIQUE,
            activo BIT NOT NULL DEFAULT 1,
            creado_en DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
            actualizado_en DATETIME2 NOT NULL DEFAULT SYSDATETIME()
        );
        CREATE INDEX IX_destinatarios_reportes_email ON dbo.destinatarios_reportes(email);
        CREATE INDEX IX_destinatarios_reportes_token_portal ON dbo.destinatarios_reportes(token_portal);
    END;

    IF OBJECT_ID('dbo.reportes_compartidos', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.reportes_compartidos (
            id UNIQUEIDENTIFIER NOT NULL PRIMARY KEY DEFAULT NEWID(),
            token_acceso VARCHAR(64) NOT NULL UNIQUE,
            codigo_corto VARCHAR(32) NOT NULL UNIQUE,
            creado_por_id INT NULL REFERENCES dbo.usuarios(id) ON DELETE SET NULL,
            destinatario_id INT NOT NULL REFERENCES dbo.destinatarios_reportes(id) ON DELETE CASCADE,
            espacio_id INT NOT NULL,
            titulo_reporte NVARCHAR(200) NOT NULL,
            finalidad_reporte NVARCHAR(500) NOT NULL,
            nota_general NVARCHAR(MAX) NULL,
            notas_items_json NVARCHAR(MAX) NULL,
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            modo_datos VARCHAR(30) NOT NULL DEFAULT 'dinamico_acotado',
            filtros_bloqueados_json NVARCHAR(MAX) NOT NULL,
            graficos_visibles_json NVARCHAR(MAX) NOT NULL,
            indicadores_visibles_json NVARCHAR(MAX) NOT NULL,
            datos_instantanea_json NVARCHAR(MAX) NULL,
            permitir_exportacion BIT NOT NULL DEFAULT 1,
            permitir_ia BIT NOT NULL DEFAULT 0,
            activo BIT NOT NULL DEFAULT 1,
            expira_en DATETIME2 NULL,
            total_accesos INT NOT NULL DEFAULT 0,
            ultimo_acceso_en DATETIME2 NULL,
            creado_en DATETIME2 NOT NULL DEFAULT SYSDATETIME()
        );
        CREATE INDEX IX_reportes_compartidos_token_acceso ON dbo.reportes_compartidos(token_acceso);
        CREATE INDEX IX_reportes_compartidos_destinatario_id ON dbo.reportes_compartidos(destinatario_id);
        CREATE INDEX IX_reportes_compartidos_creado_por_id ON dbo.reportes_compartidos(creado_por_id);
    END;

    IF OBJECT_ID('dbo.auditoria_accesos_reporte', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.auditoria_accesos_reporte (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            reporte_id UNIQUEIDENTIFIER NOT NULL REFERENCES dbo.reportes_compartidos(id) ON DELETE CASCADE,
            fecha_hora DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
            ip_origen VARCHAR(64) NULL,
            accion VARCHAR(50) NOT NULL DEFAULT 'apertura_reporte'
        );
        CREATE INDEX IX_auditoria_accesos_reporte_reporte_id ON dbo.auditoria_accesos_reporte(reporte_id);
    END;
    """)


def downgrade() -> None:
    op.execute("""
    IF OBJECT_ID('dbo.auditoria_accesos_reporte', 'U') IS NOT NULL
        DROP TABLE dbo.auditoria_accesos_reporte;
    IF OBJECT_ID('dbo.reportes_compartidos', 'U') IS NOT NULL
        DROP TABLE dbo.reportes_compartidos;
    IF OBJECT_ID('dbo.destinatarios_reportes', 'U') IS NOT NULL
        DROP TABLE dbo.destinatarios_reportes;
    """)

