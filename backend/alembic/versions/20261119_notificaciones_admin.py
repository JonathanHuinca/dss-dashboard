"""notificaciones_admin

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-19 18:55:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'notificaciones_admin')
        BEGIN
            CREATE TABLE dbo.notificaciones_admin (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                tipo NVARCHAR(50) NOT NULL CONSTRAINT df_notif_admin_tipo DEFAULT N'bloqueo_login',
                titulo NVARCHAR(150) NOT NULL,
                mensaje NVARCHAR(500) NOT NULL,
                usuario_afectado_id INT NULL,
                usuario_afectado_email NVARCHAR(150) NULL,
                usuario_afectado_nombre NVARCHAR(150) NULL,
                intentos_fallidos INT NOT NULL CONSTRAINT df_notif_admin_intentos DEFAULT 5,
                ip_origen NVARCHAR(64) NULL,
                leida BIT NOT NULL CONSTRAINT df_notif_admin_leida DEFAULT 0,
                leida_en DATETIME2 NULL,
                leida_por_id INT NULL,
                creado_en DATETIME2 NOT NULL CONSTRAINT df_notif_admin_creado_en DEFAULT GETDATE(),
                CONSTRAINT fk_notif_admin_usuario FOREIGN KEY (usuario_afectado_id)
                    REFERENCES dbo.usuarios(id) ON DELETE SET NULL
            );
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_notificaciones_admin_leida'
              AND object_id = OBJECT_ID('dbo.notificaciones_admin')
        )
        BEGIN
            CREATE INDEX ix_notificaciones_admin_leida
            ON dbo.notificaciones_admin (leida);
        END
    """)

    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_notificaciones_admin_creado_en'
              AND object_id = OBJECT_ID('dbo.notificaciones_admin')
        )
        BEGIN
            CREATE INDEX ix_notificaciones_admin_creado_en
            ON dbo.notificaciones_admin (creado_en DESC);
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (SELECT 1 FROM sys.tables WHERE name = 'notificaciones_admin')
        BEGIN
            DROP TABLE dbo.notificaciones_admin;
        END
    """)
