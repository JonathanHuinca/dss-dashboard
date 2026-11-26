"""completar_esquema_auditoria_y_bloqueo

Revision ID: 8ead4fe84114
Revises: f6a7b8c9d005
Create Date: 2026-10-26 16:16:17.707616-03:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql

# revision identifiers, used by Alembic.
revision = '8ead4fe84114'
down_revision = 'f6a7b8c9d005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tabla contingencias_academicas
    op.execute("""
    IF OBJECT_ID('dbo.contingencias_academicas', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.contingencias_academicas (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            fecha_inicio DATE NOT NULL,
            fecha_fin DATE NOT NULL,
            tipo VARCHAR(30) NOT NULL,
            titulo VARCHAR(150) NOT NULL,
            descripcion VARCHAR(MAX) NULL,
            carreras_afectadas VARCHAR(MAX) NULL,
            implica_cierre_total BIT NOT NULL,
            creado_en DATETIME2 NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    END
    """)

    # 2. Tabla horarios_operacion
    op.execute("""
    IF OBJECT_ID('dbo.horarios_operacion', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.horarios_operacion (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            espacio_id INT NOT NULL REFERENCES dbo.espacios(id),
            anio INT NOT NULL,
            descripcion VARCHAR(150) NOT NULL,
            tipo_horario VARCHAR(50) NOT NULL,
            fecha_inicio DATETIME2 NULL,
            fecha_fin DATETIME2 NULL,
            hora_apertura VARCHAR(5) NOT NULL,
            hora_cierre VARCHAR(5) NOT NULL,
            cierre_dia_siguiente BIT NOT NULL,
            es_continuo_24h BIT NOT NULL,
            configuracion_dias VARCHAR(MAX) NULL,
            activo BIT NOT NULL,
            updated_at DATETIME2 NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX ix_horarios_operacion_anio ON dbo.horarios_operacion (anio);
        CREATE INDEX ix_horarios_operacion_espacio_id ON dbo.horarios_operacion (espacio_id);
    END
    """)

    # 3. Tabla download_audit_logs
    op.execute("""
    IF OBJECT_ID('dbo.download_audit_logs', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.download_audit_logs (
            id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            usuario_id INT NULL REFERENCES dbo.usuarios(id) ON DELETE SET NULL,
            modulo VARCHAR(50) NOT NULL,
            formato VARCHAR(20) NOT NULL,
            filtro_fecha_inicio VARCHAR(30) NULL,
            filtro_fecha_fin VARCHAR(30) NULL,
            filtro_detalle VARCHAR(255) NULL,
            total_registros INT NOT NULL,
            ip_origen VARCHAR(50) NULL,
            timestamp DATETIME2 NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX ix_download_audit_logs_modulo ON dbo.download_audit_logs (modulo);
        CREATE INDEX ix_download_audit_logs_timestamp ON dbo.download_audit_logs (timestamp);
        CREATE INDEX ix_download_audit_logs_usuario_id ON dbo.download_audit_logs (usuario_id);
    END
    """)

    # 4. Columnas en calendario_academico
    op.execute("""
    IF COL_LENGTH('dbo.calendario_academico', 'is_strike_federado') IS NULL
        ALTER TABLE dbo.calendario_academico ADD is_strike_federado BIT NOT NULL DEFAULT 0;
    IF COL_LENGTH('dbo.calendario_academico', 'is_strike_carrera') IS NULL
        ALTER TABLE dbo.calendario_academico ADD is_strike_carrera BIT NOT NULL DEFAULT 0;
    IF COL_LENGTH('dbo.calendario_academico', 'tipo_contingencia') IS NULL
        ALTER TABLE dbo.calendario_academico ADD tipo_contingencia VARCHAR(50) NULL;
    """)

    # 5. Ajuste idempotente de chat_audit_logs.timestamp eliminando default e indice previos en SQL Server
    op.execute("""
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_timestamp' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        DROP INDEX ix_chat_audit_logs_timestamp ON dbo.chat_audit_logs;

    DECLARE @def_name NVARCHAR(256);
    SELECT @def_name = dc.name
    FROM sys.default_constraints dc
    JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE dc.parent_object_id = OBJECT_ID('dbo.chat_audit_logs') AND c.name = 'timestamp';

    IF @def_name IS NOT NULL
        EXEC('ALTER TABLE dbo.chat_audit_logs DROP CONSTRAINT [' + @def_name + ']');

    ALTER TABLE dbo.chat_audit_logs ALTER COLUMN timestamp DATETIMEOFFSET NOT NULL;
    ALTER TABLE dbo.chat_audit_logs ADD CONSTRAINT DF_chat_audit_logs_timestamp DEFAULT SYSDATETIMEOFFSET() FOR timestamp;
    CREATE INDEX ix_chat_audit_logs_timestamp ON dbo.chat_audit_logs (timestamp);
    """)

    # 6. Normalizacion de indices en dim_estudiante_carrera, ingestion_jobs y salas_biblioteca
    op.execute("""
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dec_matricula' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dec_matricula ON dbo.dim_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dec_person_id' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dec_person_id ON dbo.dim_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dec_rut_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dec_rut_hash ON dbo.dim_estudiante_carrera;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_matricula' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        CREATE INDEX ix_dim_estudiante_carrera_matricula ON dbo.dim_estudiante_carrera (matricula);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_person_id_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        CREATE INDEX ix_dim_estudiante_carrera_person_id_hash ON dbo.dim_estudiante_carrera (person_id_hash);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_rut_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        CREATE INDEX ix_dim_estudiante_carrera_rut_hash ON dbo.dim_estudiante_carrera (rut_hash);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ij_file_hash' AND object_id = OBJECT_ID('dbo.ingestion_jobs'))
        DROP INDEX ix_ij_file_hash ON dbo.ingestion_jobs;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ingestion_jobs_file_hash' AND object_id = OBJECT_ID('dbo.ingestion_jobs'))
        CREATE INDEX ix_ingestion_jobs_file_hash ON dbo.ingestion_jobs (file_hash);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_sb_espacio_id' AND object_id = OBJECT_ID('dbo.salas_biblioteca'))
        DROP INDEX ix_sb_espacio_id ON dbo.salas_biblioteca;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_salas_biblioteca_espacio_id' AND object_id = OBJECT_ID('dbo.salas_biblioteca'))
        CREATE INDEX ix_salas_biblioteca_espacio_id ON dbo.salas_biblioteca (espacio_id);
    """)

    # 7. Columnas de bloqueo en usuarios
    op.execute("""
    IF COL_LENGTH('dbo.usuarios', 'intentos_fallidos_login') IS NULL
        ALTER TABLE dbo.usuarios ADD intentos_fallidos_login INT NOT NULL DEFAULT 0;
    IF COL_LENGTH('dbo.usuarios', 'bloqueado_hasta') IS NULL
        ALTER TABLE dbo.usuarios ADD bloqueado_hasta DATETIMEOFFSET NULL;
    """)


def downgrade() -> None:
    op.execute("""
    -- 1. Revertir columnas agregadas a usuarios (eliminando sus default constraints primero)
    DECLARE @df_name NVARCHAR(200);
    SELECT @df_name = dc.name
    FROM sys.default_constraints dc
    JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE dc.parent_object_id = OBJECT_ID('dbo.usuarios') AND c.name = 'intentos_fallidos_login';
    IF @df_name IS NOT NULL
        EXEC('ALTER TABLE dbo.usuarios DROP CONSTRAINT [' + @df_name + ']');
    IF COL_LENGTH('dbo.usuarios', 'intentos_fallidos_login') IS NOT NULL
        ALTER TABLE dbo.usuarios DROP COLUMN intentos_fallidos_login;

    SET @df_name = NULL;
    SELECT @df_name = dc.name
    FROM sys.default_constraints dc
    JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE dc.parent_object_id = OBJECT_ID('dbo.usuarios') AND c.name = 'bloqueado_hasta';
    IF @df_name IS NOT NULL
        EXEC('ALTER TABLE dbo.usuarios DROP CONSTRAINT [' + @df_name + ']');
    IF COL_LENGTH('dbo.usuarios', 'bloqueado_hasta') IS NOT NULL
        ALTER TABLE dbo.usuarios DROP COLUMN bloqueado_hasta;

    -- 2. Revertir columnas agregadas a dim_estudiante_carrera e índices creados
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_rut_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dim_estudiante_carrera_rut_hash ON dbo.dim_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_person_id_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dim_estudiante_carrera_person_id_hash ON dbo.dim_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_matricula' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dim_estudiante_carrera_matricula ON dbo.dim_estudiante_carrera;

    -- 3. Revertir columnas agregadas a calendario_academico
    DECLARE @col_cal NVARCHAR(100), @df_cal NVARCHAR(200);
    DECLARE cur_cal CURSOR LOCAL FAST_FORWARD FOR
        SELECT c.name, dc.name
        FROM sys.default_constraints dc
        JOIN sys.columns c ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
        WHERE dc.parent_object_id = OBJECT_ID('dbo.calendario_academico')
          AND c.name IN ('is_strike_federado', 'is_strike_carrera', 'tipo_contingencia');
    OPEN cur_cal;
    FETCH NEXT FROM cur_cal INTO @col_cal, @df_cal;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC('ALTER TABLE dbo.calendario_academico DROP CONSTRAINT [' + @df_cal + ']');
        FETCH NEXT FROM cur_cal INTO @col_cal, @df_cal;
    END
    CLOSE cur_cal;
    DEALLOCATE cur_cal;

    IF COL_LENGTH('dbo.calendario_academico', 'tipo_contingencia') IS NOT NULL
        ALTER TABLE dbo.calendario_academico DROP COLUMN tipo_contingencia;
    IF COL_LENGTH('dbo.calendario_academico', 'is_strike_carrera') IS NOT NULL
        ALTER TABLE dbo.calendario_academico DROP COLUMN is_strike_carrera;
    IF COL_LENGTH('dbo.calendario_academico', 'is_strike_federado') IS NOT NULL
        ALTER TABLE dbo.calendario_academico DROP COLUMN is_strike_federado;

    -- 4. Revertir índice/default de chat_audit_logs.timestamp
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_timestamp' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        DROP INDEX ix_chat_audit_logs_timestamp ON dbo.chat_audit_logs;
    IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = 'DF_chat_audit_logs_timestamp' AND parent_object_id = OBJECT_ID('dbo.chat_audit_logs'))
        ALTER TABLE dbo.chat_audit_logs DROP CONSTRAINT DF_chat_audit_logs_timestamp;

    -- 5. Eliminar tablas creadas en esta revisión
    IF OBJECT_ID('dbo.download_audit_logs', 'U') IS NOT NULL
        DROP TABLE dbo.download_audit_logs;
    IF OBJECT_ID('dbo.horarios_operacion', 'U') IS NOT NULL
        DROP TABLE dbo.horarios_operacion;
    IF OBJECT_ID('dbo.contingencias_academicas', 'U') IS NOT NULL
        DROP TABLE dbo.contingencias_academicas;
    """)
