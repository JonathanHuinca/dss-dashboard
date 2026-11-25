"""credenciales_ia_y_smtp

Revision ID: e1f2a3b4c5d6
Revises: d9e8f7a6b5c4
Create Date: 2026-11-19 10:30:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "d9e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'credenciales_proveedores_ia')
        BEGIN
            CREATE TABLE dbo.credenciales_proveedores_ia (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                nombre NVARCHAR(100) NOT NULL,
                provider_id NVARCHAR(50) NOT NULL,
                modelo NVARCHAR(120) NOT NULL,
                base_url NVARCHAR(300) NULL,
                encrypted_api_key NVARCHAR(MAX) NULL,
                key_hint NVARCHAR(32) NOT NULL CONSTRAINT df_cred_ia_key_hint DEFAULT N'',
                es_activa BIT NOT NULL CONSTRAINT df_cred_ia_es_activa DEFAULT 0,
                ultimo_test_ok BIT NULL,
                ultimo_test_en DATETIME2 NULL,
                creado_por_id INT NULL,
                created_at DATETIME2 NOT NULL CONSTRAINT df_cred_ia_created_at DEFAULT GETDATE(),
                updated_at DATETIME2 NOT NULL CONSTRAINT df_cred_ia_updated_at DEFAULT GETDATE(),
                CONSTRAINT fk_cred_ia_usuario FOREIGN KEY (creado_por_id)
                    REFERENCES dbo.usuarios(id) ON DELETE SET NULL
            );
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_credenciales_proveedores_ia_provider_id'
              AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia')
        )
        BEGIN
            CREATE INDEX ix_credenciales_proveedores_ia_provider_id
            ON dbo.credenciales_proveedores_ia (provider_id);
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_credenciales_proveedores_ia_es_activa'
              AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia')
        )
        BEGIN
            CREATE INDEX ix_credenciales_proveedores_ia_es_activa
            ON dbo.credenciales_proveedores_ia (es_activa);
        END
    """)

    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'configuracion_smtp')
        BEGIN
            CREATE TABLE dbo.configuracion_smtp (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                nombre NVARCHAR(100) NOT NULL,
                host NVARCHAR(200) NOT NULL,
                port INT NOT NULL CONSTRAINT df_smtp_port DEFAULT 587,
                use_tls BIT NOT NULL CONSTRAINT df_smtp_use_tls DEFAULT 1,
                use_ssl BIT NOT NULL CONSTRAINT df_smtp_use_ssl DEFAULT 0,
                username NVARCHAR(200) NOT NULL,
                from_email NVARCHAR(200) NOT NULL,
                from_name NVARCHAR(150) NOT NULL CONSTRAINT df_smtp_from_name DEFAULT N'Sistema DSS Campus San Francisco UCT',
                encrypted_password NVARCHAR(MAX) NOT NULL,
                password_hint NVARCHAR(32) NOT NULL CONSTRAINT df_smtp_pwd_hint DEFAULT N'',
                es_activa BIT NOT NULL CONSTRAINT df_smtp_es_activa DEFAULT 0,
                ultimo_test_ok BIT NULL,
                ultimo_test_en DATETIME2 NULL,
                creado_por_id INT NULL,
                created_at DATETIME2 NOT NULL CONSTRAINT df_smtp_created_at DEFAULT GETDATE(),
                updated_at DATETIME2 NOT NULL CONSTRAINT df_smtp_updated_at DEFAULT GETDATE(),
                CONSTRAINT fk_smtp_usuario FOREIGN KEY (creado_por_id)
                    REFERENCES dbo.usuarios(id) ON DELETE SET NULL
            );
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_configuracion_smtp_es_activa'
              AND object_id = OBJECT_ID('dbo.configuracion_smtp')
        )
        BEGIN
            CREATE INDEX ix_configuracion_smtp_es_activa
            ON dbo.configuracion_smtp (es_activa);
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'configuracion_smtp')
        BEGIN
            DROP TABLE dbo.configuracion_smtp;
        END
    """)

    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'credenciales_proveedores_ia')
        BEGIN
            DROP TABLE dbo.credenciales_proveedores_ia;
        END
    """)
