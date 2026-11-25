"""Agregar mensajes_ia_reporte y trazabilidad completa en chat_audit_logs

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-11-24 12:30:00.000000

"""
from typing import Sequence, Union
from alembic import op

revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        IF OBJECT_ID('mensajes_ia_reporte', 'U') IS NULL
        BEGIN
            CREATE TABLE mensajes_ia_reporte (
                id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
                reporte_id UNIQUEIDENTIFIER NOT NULL
                    CONSTRAINT fk_mensajes_ia_reporte_rep
                    FOREIGN KEY REFERENCES reportes_compartidos(id) ON DELETE CASCADE,
                sesion_id NVARCHAR(64) NOT NULL CONSTRAINT df_mensajes_ia_rep_sesion DEFAULT 'principal',
                usuario_id INT NULL
                    CONSTRAINT fk_mensajes_ia_reporte_usr
                    FOREIGN KEY REFERENCES usuarios(id) ON DELETE SET NULL,
                pregunta NVARCHAR(MAX) NOT NULL,
                respuesta NVARCHAR(MAX) NOT NULL,
                modelo_utilizado NVARCHAR(100) NULL,
                tiempo_respuesta_ms FLOAT NULL,
                creado_en DATETIME2 NOT NULL CONSTRAINT df_mensajes_ia_rep_fecha DEFAULT GETDATE()
            );
        END
        """
    )
    op.execute(
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_mensajes_ia_reporte_rep_fecha'
              AND object_id = OBJECT_ID('mensajes_ia_reporte')
        )
        BEGIN
            CREATE INDEX ix_mensajes_ia_reporte_rep_fecha
            ON mensajes_ia_reporte (reporte_id, creado_en ASC);
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'respuesta_text') IS NULL
        BEGIN
            ALTER TABLE chat_audit_logs ADD respuesta_text NVARCHAR(MAX) NULL;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'origen') IS NULL
        BEGIN
            ALTER TABLE chat_audit_logs
            ADD origen NVARCHAR(30) NOT NULL CONSTRAINT df_chat_audit_origen DEFAULT 'dashboard';
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'reporte_codigo') IS NULL
        BEGIN
            ALTER TABLE chat_audit_logs ADD reporte_codigo NVARCHAR(32) NULL;
        END
        """
    )
    op.execute(
        """
        UPDATE chat_audit_logs SET status = N'éxito' WHERE status = 'success';
        """
    )
    op.execute(
        """
        UPDATE chat_audit_logs
        SET origen = 'reporte_compartido'
        WHERE prompt_text LIKE '[[]Reporte %' AND origen = 'dashboard';
        """
    )


def downgrade() -> None:
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'reporte_codigo') IS NOT NULL
        BEGIN
            ALTER TABLE chat_audit_logs DROP COLUMN reporte_codigo;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'origen') IS NOT NULL
        BEGIN
            DECLARE @df_name NVARCHAR(128);
            SELECT @df_name = dc.name
            FROM sys.default_constraints dc
            INNER JOIN sys.columns c
                ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
            WHERE dc.parent_object_id = OBJECT_ID('chat_audit_logs') AND c.name = 'origen';
            IF @df_name IS NOT NULL
                EXEC('ALTER TABLE chat_audit_logs DROP CONSTRAINT ' + @df_name);
            ALTER TABLE chat_audit_logs DROP COLUMN origen;
        END
        """
    )
    op.execute(
        """
        IF COL_LENGTH('chat_audit_logs', 'respuesta_text') IS NOT NULL
        BEGIN
            ALTER TABLE chat_audit_logs DROP COLUMN respuesta_text;
        END
        """
    )
    op.execute(
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_mensajes_ia_reporte_rep_fecha'
              AND object_id = OBJECT_ID('mensajes_ia_reporte')
        )
        BEGIN
            DROP INDEX ix_mensajes_ia_reporte_rep_fecha ON mensajes_ia_reporte;
        END
        """
    )
    op.execute(
        """
        IF OBJECT_ID('mensajes_ia_reporte', 'U') IS NOT NULL
        BEGIN
            DROP TABLE mensajes_ia_reporte;
        END
        """
    )
