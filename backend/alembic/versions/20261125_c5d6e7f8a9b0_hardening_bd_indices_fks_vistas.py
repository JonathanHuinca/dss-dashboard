"""Hardening estructural BD: FKs, CHECKs, indices cubrientes, vistas NOEXPAND y unicidad

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-11-25 23:55:00.000000-03:00

"""
from typing import Sequence, Union
from alembic import op

revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Eliminar vistas indexadas SCHEMABINDING antes de reestructurar índices base
    #    asistencia_diaria_biblioteca y vehiculos_composicion_flota se retiran definitivamente (sin uso).
    op.execute("""
    SET ANSI_NULLS ON;
    SET QUOTED_IDENTIFIER ON;

    DROP VIEW IF EXISTS dbo.asistencia_diaria_biblioteca;
    DROP VIEW IF EXISTS dbo.vehiculos_composicion_flota;
    DROP VIEW IF EXISTS dbo.aforo_horario_biblioteca;
    DROP VIEW IF EXISTS dbo.aforo_horario_estacionamiento;
    DROP VIEW IF EXISTS dbo.vehiculos_diario_estacionamiento;
    """)

    # 2. Reestructurar clustered + consolidar índices B-tree en eventos_asistencia y eventos_vehiculares
    op.execute("""
    SET ANSI_NULLS ON;
    SET QUOTED_IDENTIFIER ON;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'CCI_eventos_asistencia' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        DROP INDEX CCI_eventos_asistencia ON dbo.eventos_asistencia;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.eventos_asistencia') AND index_id = 1)
        CREATE CLUSTERED INDEX CX_eventos_asistencia_espacio_time ON dbo.eventos_asistencia (espacio_id, time);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ea_espacio_time' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        DROP INDEX ix_ea_espacio_time ON dbo.eventos_asistencia;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ea_cobertura_analitica' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        DROP INDEX IX_ea_cobertura_analitica ON dbo.eventos_asistencia;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ea_espacio_time_covering' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        DROP INDEX ix_ea_espacio_time_covering ON dbo.eventos_asistencia;

    CREATE NONCLUSTERED INDEX ix_ea_espacio_time_covering
    ON dbo.eventos_asistencia (espacio_id, time, alerta_coherencia_fechas)
    INCLUDE (person_id_hash, permanencia_min, marcajes_totales, door_entrada, door_salida, carrera, facultad, primera_entrada, ultima_salida, salida_imputada);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_espacio_time' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX ix_ev_espacio_time ON dbo.eventos_vehiculares;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ev_cobertura_analitica' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX IX_ev_cobertura_analitica ON dbo.eventos_vehiculares;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_espacio_time_covering' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX ix_ev_espacio_time_covering ON dbo.eventos_vehiculares;

    CREATE NONCLUSTERED INDEX ix_ev_espacio_time_covering
    ON dbo.eventos_vehiculares (espacio_id, time, direccion, calidad_lectura)
    INCLUDE (patente_hash, camara, tipo_vehiculo, marca);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_patente_time' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX ix_ev_patente_time ON dbo.eventos_vehiculares;

    CREATE NONCLUSTERED INDEX ix_ev_patente_time
    ON dbo.eventos_vehiculares (patente_hash, time)
    INCLUDE (espacio_id, camara, direccion);
    """)

    # 3. Actualizar CHECK CONSTRAINTS y restaurar confianza (WITH CHECK)
    op.execute("""
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ij_tipo' AND parent_object_id = OBJECT_ID('dbo.ingestion_jobs'))
        ALTER TABLE dbo.ingestion_jobs DROP CONSTRAINT ck_ij_tipo;

    ALTER TABLE dbo.ingestion_jobs WITH CHECK ADD CONSTRAINT ck_ij_tipo
    CHECK (tipo IN ('asistencia', 'marcajes_torniquete', 'vehicular', 'vehicular_anpr', 'academico', 'curricular', 'custom', 'institucional_uct'));

    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ejecuciones_tareas_disparador' AND parent_object_id = OBJECT_ID('dbo.ejecuciones_tareas'))
        ALTER TABLE dbo.ejecuciones_tareas DROP CONSTRAINT ck_ejecuciones_tareas_disparador;

    ALTER TABLE dbo.ejecuciones_tareas WITH CHECK ADD CONSTRAINT ck_ejecuciones_tareas_disparador
    CHECK (disparador IN ('programado', 'manual', 'recuperacion', 'reintento'));

    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ij_estado' AND is_not_trusted = 1)
        ALTER TABLE dbo.ingestion_jobs WITH CHECK CHECK CONSTRAINT ck_ij_estado;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ejecuciones_tareas_estado' AND is_not_trusted = 1)
        ALTER TABLE dbo.ejecuciones_tareas WITH CHECK CHECK CONSTRAINT ck_ejecuciones_tareas_estado;
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_estado_calendario_anual_estado' AND is_not_trusted = 1)
        ALTER TABLE dbo.estado_calendario_anual WITH CHECK CHECK CONSTRAINT ck_estado_calendario_anual_estado;
    """)

    # 4. Restricciones UNIQUE e índices únicos filtrados WHERE es_activa = 1
    op.execute("""
    SET ANSI_NULLS ON;
    SET QUOTED_IDENTIFIER ON;

    IF NOT EXISTS (
        SELECT 1 FROM sys.key_constraints
        WHERE parent_object_id = OBJECT_ID('dbo.configuracion_espacios') AND type = 'UQ'
    )
    AND NOT EXISTS (
        SELECT 1 FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        WHERE i.object_id = OBJECT_ID('dbo.configuracion_espacios') AND i.is_unique = 1 AND c.name = 'espacio_id'
    )
    BEGIN
        ALTER TABLE dbo.configuracion_espacios ADD CONSTRAINT uq_configuracion_espacios_espacio_id UNIQUE (espacio_id);
    END

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_esf_fuente_espacio' AND object_id = OBJECT_ID('dbo.estado_sincronizacion_fuente') AND is_unique = 0)
        DROP INDEX ix_esf_fuente_espacio ON dbo.estado_sincronizacion_fuente;

    IF NOT EXISTS (
        SELECT 1 FROM sys.key_constraints
        WHERE name = 'uq_estado_sincronizacion_fuente_espacio' AND parent_object_id = OBJECT_ID('dbo.estado_sincronizacion_fuente')
    )
    BEGIN
        ALTER TABLE dbo.estado_sincronizacion_fuente ADD CONSTRAINT uq_estado_sincronizacion_fuente_espacio UNIQUE (fuente, espacio_id);
    END

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_credenciales_proveedores_ia_es_activa' AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia'))
        DROP INDEX ix_credenciales_proveedores_ia_es_activa ON dbo.credenciales_proveedores_ia;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_credenciales_ia_unica_activa' AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia'))
        CREATE UNIQUE NONCLUSTERED INDEX ux_credenciales_ia_unica_activa ON dbo.credenciales_proveedores_ia (es_activa) WHERE es_activa = 1;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_configuracion_smtp_es_activa' AND object_id = OBJECT_ID('dbo.configuracion_smtp'))
        DROP INDEX ix_configuracion_smtp_es_activa ON dbo.configuracion_smtp;

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_configuracion_smtp_unica_activa' AND object_id = OBJECT_ID('dbo.configuracion_smtp'))
        CREATE UNIQUE NONCLUSTERED INDEX ux_configuracion_smtp_unica_activa ON dbo.configuracion_smtp (es_activa) WHERE es_activa = 1;
    """)

    # 5. Claves foráneas faltantes, ON DELETE SET NULL en ingestion_jobs.creado_por y FKs UCT
    op.execute("""
    -- ingestion_jobs.espacio_id -> espacios(id)
    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        WHERE fk.parent_object_id = OBJECT_ID('dbo.ingestion_jobs')
          AND COL_NAME(fkc.parent_object_id, fkc.parent_column_id) = 'espacio_id'
    )
    BEGIN
        ALTER TABLE dbo.ingestion_jobs WITH CHECK
        ADD CONSTRAINT fk_ingestion_jobs_espacio_id FOREIGN KEY (espacio_id) REFERENCES dbo.espacios(id);
    END

    -- ingestion_jobs.creado_por -> usuarios(id) ON DELETE SET NULL
    DECLARE @fk_ij_usr NVARCHAR(200);
    SELECT @fk_ij_usr = fk.name
    FROM sys.foreign_keys fk
    JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    WHERE fk.parent_object_id = OBJECT_ID('dbo.ingestion_jobs')
      AND COL_NAME(fkc.parent_object_id, fkc.parent_column_id) = 'creado_por'
      AND fk.delete_referential_action <> 2; -- 2 = SET_NULL
    IF @fk_ij_usr IS NOT NULL
        EXEC('ALTER TABLE dbo.ingestion_jobs DROP CONSTRAINT [' + @fk_ij_usr + ']');

    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        WHERE fk.parent_object_id = OBJECT_ID('dbo.ingestion_jobs')
          AND COL_NAME(fkc.parent_object_id, fkc.parent_column_id) = 'creado_por'
    )
    BEGIN
        ALTER TABLE dbo.ingestion_jobs WITH CHECK
        ADD CONSTRAINT fk_ingestion_jobs_creado_por FOREIGN KEY (creado_por) REFERENCES dbo.usuarios(id) ON DELETE SET NULL;
    END

    -- contingencias_academicas.espacio_id -> espacios(id)
    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        WHERE fk.parent_object_id = OBJECT_ID('dbo.contingencias_academicas')
          AND COL_NAME(fkc.parent_object_id, fkc.parent_column_id) = 'espacio_id'
    )
    BEGIN
        ALTER TABLE dbo.contingencias_academicas WITH CHECK
        ADD CONSTRAINT fk_contingencias_academicas_espacio_id FOREIGN KEY (espacio_id) REFERENCES dbo.espacios(id);
    END

    -- reportes_compartidos.espacio_id -> espacios(id)
    IF NOT EXISTS (
        SELECT 1 FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        WHERE fk.parent_object_id = OBJECT_ID('dbo.reportes_compartidos')
          AND COL_NAME(fkc.parent_object_id, fkc.parent_column_id) = 'espacio_id'
    )
    BEGIN
        ALTER TABLE dbo.reportes_compartidos WITH CHECK
        ADD CONSTRAINT fk_reportes_compartidos_espacio_id FOREIGN KEY (espacio_id) REFERENCES dbo.espacios(id);
    END

    -- FKs en tablas institucionales uct_* (uct_estudiante_carrera.estd_rut_hash omitida intencionalmente porque uct_estudiante contiene muestra parcial)
    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_ambiente_campus')
        ALTER TABLE dbo.uct_ambiente WITH CHECK ADD CONSTRAINT fk_uct_ambiente_campus FOREIGN KEY (camp_codigo) REFERENCES dbo.uct_campus(camp_codigo_campus);

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_campus_campus')
        ALTER TABLE dbo.uct_carrera_campus WITH CHECK ADD CONSTRAINT fk_uct_carrera_campus_campus FOREIGN KEY (camp_codigo) REFERENCES dbo.uct_campus(camp_codigo_campus);

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_programa_tipo')
        ALTER TABLE dbo.uct_carrera_programa WITH CHECK ADD CONSTRAINT fk_uct_carrera_programa_tipo FOREIGN KEY (tcar_codigo, clac_codigo) REFERENCES dbo.uct_tipo_carrera(tcar_codigo, clac_codigo);

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_situacion')
        ALTER TABLE dbo.uct_estudiante_carrera WITH CHECK ADD CONSTRAINT fk_uct_est_carrera_situacion FOREIGN KEY (salu_codigo) REFERENCES dbo.uct_situacion_alumno(salu_codigo);

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_via')
        ALTER TABLE dbo.uct_estudiante_carrera WITH CHECK ADD CONSTRAINT fk_uct_est_carrera_via FOREIGN KEY (ving_codigo) REFERENCES dbo.uct_vias_ingreso(ving_codigo);

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_campus_carrera')
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM dbo.uct_carrera_campus WHERE carr_codigo NOT IN (SELECT carr_codigo FROM dbo.uct_carrera_programa))
            ALTER TABLE dbo.uct_carrera_campus WITH CHECK ADD CONSTRAINT fk_uct_carrera_campus_carrera FOREIGN KEY (carr_codigo) REFERENCES dbo.uct_carrera_programa(carr_codigo);
        ELSE
            ALTER TABLE dbo.uct_carrera_campus WITH NOCHECK ADD CONSTRAINT fk_uct_carrera_campus_carrera FOREIGN KEY (carr_codigo) REFERENCES dbo.uct_carrera_programa(carr_codigo);
    END

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_carrera')
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM dbo.uct_estudiante_carrera WHERE carr_codigo IS NOT NULL AND carr_codigo NOT IN (SELECT carr_codigo FROM dbo.uct_carrera_programa))
            ALTER TABLE dbo.uct_estudiante_carrera WITH CHECK ADD CONSTRAINT fk_uct_est_carrera_carrera FOREIGN KEY (carr_codigo) REFERENCES dbo.uct_carrera_programa(carr_codigo);
        ELSE
            ALTER TABLE dbo.uct_estudiante_carrera WITH NOCHECK ADD CONSTRAINT fk_uct_est_carrera_carrera FOREIGN KEY (carr_codigo) REFERENCES dbo.uct_carrera_programa(carr_codigo);
    END
    """)

    # 6. Eliminar índices duplicados sobre columnas UNIQUE/prefijos y crear índices compuestos faltantes
    op.execute("""
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_destinatarios_reportes_email' AND object_id = OBJECT_ID('dbo.destinatarios_reportes'))
        DROP INDEX IX_destinatarios_reportes_email ON dbo.destinatarios_reportes;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_destinatarios_reportes_token_portal' AND object_id = OBJECT_ID('dbo.destinatarios_reportes'))
        DROP INDEX IX_destinatarios_reportes_token_portal ON dbo.destinatarios_reportes;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_reportes_compartidos_token_acceso' AND object_id = OBJECT_ID('dbo.reportes_compartidos'))
        DROP INDEX IX_reportes_compartidos_token_acceso ON dbo.reportes_compartidos;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dec_person_id' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dec_person_id ON dbo.dim_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dim_estudiante_carrera_person_id_hash' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        DROP INDEX ix_dim_estudiante_carrera_person_id_hash ON dbo.dim_estudiante_carrera;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ejecuciones_tareas_tarea' AND object_id = OBJECT_ID('dbo.ejecuciones_tareas'))
        DROP INDEX ix_ejecuciones_tareas_tarea ON dbo.ejecuciones_tareas;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ejecuciones_tareas_tarea_inicio' AND object_id = OBJECT_ID('dbo.ejecuciones_tareas'))
        DROP INDEX ix_ejecuciones_tareas_tarea_inicio ON dbo.ejecuciones_tareas;
    CREATE NONCLUSTERED INDEX ix_ejecuciones_tareas_tarea_inicio ON dbo.ejecuciones_tareas (tarea, inicio_en DESC);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_auditoria_accesos_reporte_reporte_id' AND object_id = OBJECT_ID('dbo.auditoria_accesos_reporte'))
        DROP INDEX IX_auditoria_accesos_reporte_reporte_id ON dbo.auditoria_accesos_reporte;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_mensajes_conversacion_id' AND object_id = OBJECT_ID('dbo.chat_mensajes'))
        DROP INDEX ix_chat_mensajes_conversacion_id ON dbo.chat_mensajes;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_conversaciones_usuario_id' AND object_id = OBJECT_ID('dbo.chat_conversaciones'))
        DROP INDEX ix_chat_conversaciones_usuario_id ON dbo.chat_conversaciones;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_uct_estudiante_carrera_estu_registro' AND object_id = OBJECT_ID('dbo.uct_estudiante_carrera'))
        DROP INDEX ix_uct_estudiante_carrera_estu_registro ON dbo.uct_estudiante_carrera;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_uct_estudiante_carrera_estd_rut_hash' AND object_id = OBJECT_ID('dbo.uct_estudiante_carrera'))
        DROP INDEX ix_uct_estudiante_carrera_estd_rut_hash ON dbo.uct_estudiante_carrera;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_usuario_id' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        DROP INDEX ix_chat_audit_logs_usuario_id ON dbo.chat_audit_logs;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_usuario_ts' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        CREATE NONCLUSTERED INDEX ix_chat_audit_logs_usuario_ts ON dbo.chat_audit_logs (usuario_id, timestamp DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ingestion_jobs_creado_en' AND object_id = OBJECT_ID('dbo.ingestion_jobs'))
        CREATE NONCLUSTERED INDEX ix_ingestion_jobs_creado_en ON dbo.ingestion_jobs (creado_en DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_contingencias_fechas' AND object_id = OBJECT_ID('dbo.contingencias_academicas'))
        CREATE NONCLUSTERED INDEX ix_contingencias_fechas ON dbo.contingencias_academicas (fecha_inicio, fecha_fin) INCLUDE (espacio_id, implica_cierre_total, subespacio);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_reportes_compartidos_espacio_id' AND object_id = OBJECT_ID('dbo.reportes_compartidos'))
        CREATE NONCLUSTERED INDEX ix_reportes_compartidos_espacio_id ON dbo.reportes_compartidos (espacio_id);
    """)

    # 7. Recrear las 3 vistas indexadas activas con clave (espacio_id, ...) y semántica corregida
    op.execute("""
    SET ANSI_NULLS ON;
    SET QUOTED_IDENTIFIER ON;
    EXEC('
    CREATE VIEW dbo.aforo_horario_biblioteca WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS bucket,
        COUNT_BIG(*) AS count_rows,
        COUNT_BIG(*) AS ingresos,
        SUM(CASE WHEN salida_imputada = 0 THEN 1 ELSE 0 END) AS salidas,
        COUNT_BIG(*) AS personas_unicas
    FROM dbo.eventos_asistencia
    GROUP BY espacio_id, DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_aforo_biblioteca_bucket ON dbo.aforo_horario_biblioteca (espacio_id, bucket);

    EXEC('
    CREATE VIEW dbo.aforo_horario_estacionamiento WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        camara,
        DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS bucket,
        COUNT_BIG(*) AS count_rows,
        SUM(CASE WHEN direccion = ''entrada'' THEN 1 ELSE 0 END) AS entradas,
        SUM(CASE WHEN direccion = ''salida'' THEN 1 ELSE 0 END) AS salidas,
        SUM(CASE WHEN calidad_lectura = ''unknown'' THEN 1 ELSE 0 END) AS lecturas_fallidas
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, camara, DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_aforo_estacionamiento_bucket ON dbo.aforo_horario_estacionamiento (espacio_id, bucket, camara);

    EXEC('
    CREATE VIEW dbo.vehiculos_diario_estacionamiento WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        camara,
        direccion,
        DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS fecha_dia,
        COUNT_BIG(*) AS total_eventos
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, camara, direccion, DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_vehiculos_diario_estacionamiento ON dbo.vehiculos_diario_estacionamiento (espacio_id, fecha_dia, camara, direccion);
    """)


def downgrade() -> None:
    op.execute("""
    SET ANSI_NULLS ON;
    SET QUOTED_IDENTIFIER ON;

    DROP VIEW IF EXISTS dbo.vehiculos_diario_estacionamiento;
    DROP VIEW IF EXISTS dbo.aforo_horario_estacionamiento;
    DROP VIEW IF EXISTS dbo.aforo_horario_biblioteca;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_reportes_compartidos_espacio_id' AND object_id = OBJECT_ID('dbo.reportes_compartidos'))
        DROP INDEX ix_reportes_compartidos_espacio_id ON dbo.reportes_compartidos;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_contingencias_fechas' AND object_id = OBJECT_ID('dbo.contingencias_academicas'))
        DROP INDEX ix_contingencias_fechas ON dbo.contingencias_academicas;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ingestion_jobs_creado_en' AND object_id = OBJECT_ID('dbo.ingestion_jobs'))
        DROP INDEX ix_ingestion_jobs_creado_en ON dbo.ingestion_jobs;
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_usuario_ts' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        DROP INDEX ix_chat_audit_logs_usuario_ts ON dbo.chat_audit_logs;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_chat_audit_logs_usuario_id' AND object_id = OBJECT_ID('dbo.chat_audit_logs'))
        CREATE NONCLUSTERED INDEX ix_chat_audit_logs_usuario_id ON dbo.chat_audit_logs (usuario_id);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ejecuciones_tareas_tarea' AND object_id = OBJECT_ID('dbo.ejecuciones_tareas'))
        CREATE NONCLUSTERED INDEX ix_ejecuciones_tareas_tarea ON dbo.ejecuciones_tareas (tarea);
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ejecuciones_tareas_tarea_inicio' AND object_id = OBJECT_ID('dbo.ejecuciones_tareas'))
        DROP INDEX ix_ejecuciones_tareas_tarea_inicio ON dbo.ejecuciones_tareas;
    CREATE NONCLUSTERED INDEX ix_ejecuciones_tareas_tarea_inicio ON dbo.ejecuciones_tareas (tarea, inicio_en);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_dec_person_id' AND object_id = OBJECT_ID('dbo.dim_estudiante_carrera'))
        CREATE NONCLUSTERED INDEX ix_dec_person_id ON dbo.dim_estudiante_carrera (person_id_hash);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_uct_estudiante_carrera_estu_registro' AND object_id = OBJECT_ID('dbo.uct_estudiante_carrera'))
        CREATE NONCLUSTERED INDEX ix_uct_estudiante_carrera_estu_registro ON dbo.uct_estudiante_carrera (estu_registro);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_uct_estudiante_carrera_estd_rut_hash' AND object_id = OBJECT_ID('dbo.uct_estudiante_carrera'))
        CREATE NONCLUSTERED INDEX ix_uct_estudiante_carrera_estd_rut_hash ON dbo.uct_estudiante_carrera (estd_rut_hash);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_auditoria_accesos_reporte_reporte_id' AND object_id = OBJECT_ID('dbo.auditoria_accesos_reporte'))
        CREATE NONCLUSTERED INDEX IX_auditoria_accesos_reporte_reporte_id ON dbo.auditoria_accesos_reporte (reporte_id);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_reportes_compartidos_token_acceso' AND object_id = OBJECT_ID('dbo.reportes_compartidos'))
        CREATE NONCLUSTERED INDEX IX_reportes_compartidos_token_acceso ON dbo.reportes_compartidos (token_acceso);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_destinatarios_reportes_email' AND object_id = OBJECT_ID('dbo.destinatarios_reportes'))
        CREATE NONCLUSTERED INDEX IX_destinatarios_reportes_email ON dbo.destinatarios_reportes (email);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_destinatarios_reportes_token_portal' AND object_id = OBJECT_ID('dbo.destinatarios_reportes'))
        CREATE NONCLUSTERED INDEX IX_destinatarios_reportes_token_portal ON dbo.destinatarios_reportes (token_portal);

    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_carrera')
        ALTER TABLE dbo.uct_estudiante_carrera DROP CONSTRAINT fk_uct_est_carrera_carrera;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_campus_carrera')
        ALTER TABLE dbo.uct_carrera_campus DROP CONSTRAINT fk_uct_carrera_campus_carrera;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_via')
        ALTER TABLE dbo.uct_estudiante_carrera DROP CONSTRAINT fk_uct_est_carrera_via;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_est_carrera_situacion')
        ALTER TABLE dbo.uct_estudiante_carrera DROP CONSTRAINT fk_uct_est_carrera_situacion;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_programa_tipo')
        ALTER TABLE dbo.uct_carrera_programa DROP CONSTRAINT fk_uct_carrera_programa_tipo;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_carrera_campus_campus')
        ALTER TABLE dbo.uct_carrera_campus DROP CONSTRAINT fk_uct_carrera_campus_campus;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_uct_ambiente_campus')
        ALTER TABLE dbo.uct_ambiente DROP CONSTRAINT fk_uct_ambiente_campus;

    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_reportes_compartidos_espacio_id')
        ALTER TABLE dbo.reportes_compartidos DROP CONSTRAINT fk_reportes_compartidos_espacio_id;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_contingencias_academicas_espacio_id')
        ALTER TABLE dbo.contingencias_academicas DROP CONSTRAINT fk_contingencias_academicas_espacio_id;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_ingestion_jobs_espacio_id')
        ALTER TABLE dbo.ingestion_jobs DROP CONSTRAINT fk_ingestion_jobs_espacio_id;
    IF EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'fk_ingestion_jobs_creado_por')
        ALTER TABLE dbo.ingestion_jobs DROP CONSTRAINT fk_ingestion_jobs_creado_por;

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_configuracion_smtp_unica_activa' AND object_id = OBJECT_ID('dbo.configuracion_smtp'))
        DROP INDEX ux_configuracion_smtp_unica_activa ON dbo.configuracion_smtp;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_configuracion_smtp_es_activa' AND object_id = OBJECT_ID('dbo.configuracion_smtp'))
        CREATE NONCLUSTERED INDEX ix_configuracion_smtp_es_activa ON dbo.configuracion_smtp (es_activa);

    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ux_credenciales_ia_unica_activa' AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia'))
        DROP INDEX ux_credenciales_ia_unica_activa ON dbo.credenciales_proveedores_ia;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_credenciales_proveedores_ia_es_activa' AND object_id = OBJECT_ID('dbo.credenciales_proveedores_ia'))
        CREATE NONCLUSTERED INDEX ix_credenciales_proveedores_ia_es_activa ON dbo.credenciales_proveedores_ia (es_activa);

    IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'uq_estado_sincronizacion_fuente_espacio' AND parent_object_id = OBJECT_ID('dbo.estado_sincronizacion_fuente'))
        ALTER TABLE dbo.estado_sincronizacion_fuente DROP CONSTRAINT uq_estado_sincronizacion_fuente_espacio;
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_esf_fuente_espacio' AND object_id = OBJECT_ID('dbo.estado_sincronizacion_fuente'))
        CREATE NONCLUSTERED INDEX ix_esf_fuente_espacio ON dbo.estado_sincronizacion_fuente (fuente, espacio_id);

    IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = 'uq_configuracion_espacios_espacio_id' AND parent_object_id = OBJECT_ID('dbo.configuracion_espacios'))
        ALTER TABLE dbo.configuracion_espacios DROP CONSTRAINT uq_configuracion_espacios_espacio_id;

    -- Restaurar CHECKs previos (sin 'reintento' ni 'institucional_uct' si no hay filas incompatibles)
    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ejecuciones_tareas_disparador')
        ALTER TABLE dbo.ejecuciones_tareas DROP CONSTRAINT ck_ejecuciones_tareas_disparador;
    IF NOT EXISTS (SELECT 1 FROM dbo.ejecuciones_tareas WHERE disparador NOT IN ('programado', 'manual', 'recuperacion'))
        ALTER TABLE dbo.ejecuciones_tareas ADD CONSTRAINT ck_ejecuciones_tareas_disparador CHECK (disparador IN ('programado', 'manual', 'recuperacion'));

    IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'ck_ij_tipo')
        ALTER TABLE dbo.ingestion_jobs DROP CONSTRAINT ck_ij_tipo;
    IF NOT EXISTS (SELECT 1 FROM dbo.ingestion_jobs WHERE tipo NOT IN ('asistencia', 'vehicular', 'academico', 'curricular', 'custom'))
        ALTER TABLE dbo.ingestion_jobs ADD CONSTRAINT ck_ij_tipo CHECK (tipo IN ('asistencia', 'vehicular', 'academico', 'curricular', 'custom'));

    -- Restaurar índices previos en eventos_asistencia / eventos_vehiculares para mantener compatibilidad downgrade
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_patente_time' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX ix_ev_patente_time ON dbo.eventos_vehiculares;
    CREATE NONCLUSTERED INDEX ix_ev_patente_time ON dbo.eventos_vehiculares (patente_hash, time);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_espacio_time' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        CREATE NONCLUSTERED INDEX ix_ev_espacio_time ON dbo.eventos_vehiculares (espacio_id, time);
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ev_espacio_time_covering' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        DROP INDEX ix_ev_espacio_time_covering ON dbo.eventos_vehiculares;
    CREATE NONCLUSTERED INDEX ix_ev_espacio_time_covering ON dbo.eventos_vehiculares (espacio_id, time) INCLUDE (patente_hash, direccion, camara, calidad_lectura, tipo_vehiculo);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ev_cobertura_analitica' AND object_id = OBJECT_ID('dbo.eventos_vehiculares'))
        CREATE NONCLUSTERED INDEX IX_ev_cobertura_analitica ON dbo.eventos_vehiculares (espacio_id, time, direccion, calidad_lectura) INCLUDE (patente_hash, camara, tipo_vehiculo, marca);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ea_espacio_time' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        CREATE NONCLUSTERED INDEX ix_ea_espacio_time ON dbo.eventos_asistencia (espacio_id, time);
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'ix_ea_espacio_time_covering' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        DROP INDEX ix_ea_espacio_time_covering ON dbo.eventos_asistencia;
    CREATE NONCLUSTERED INDEX ix_ea_espacio_time_covering ON dbo.eventos_asistencia (espacio_id, time) INCLUDE (person_id_hash, permanencia_min, marcajes_totales, alerta_coherencia_fechas, door_entrada, door_salida, carrera, facultad, primera_entrada, ultima_salida, salida_imputada);
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_ea_cobertura_analitica' AND object_id = OBJECT_ID('dbo.eventos_asistencia'))
        CREATE NONCLUSTERED INDEX IX_ea_cobertura_analitica ON dbo.eventos_asistencia (espacio_id, time, alerta_coherencia_fechas) INCLUDE (person_id_hash, door_entrada, door_salida, salida_imputada, permanencia_min, marcajes_totales, carrera, facultad);

    -- Recrear las vistas indexadas originales
    EXEC('
    CREATE VIEW dbo.aforo_horario_biblioteca WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS bucket,
        COUNT_BIG(*) AS count_rows,
        SUM(CASE WHEN salida_imputada = 0 THEN 1 ELSE 0 END) AS ingresos,
        SUM(CASE WHEN salida_imputada = 1 THEN 1 ELSE 0 END) AS salidas,
        SUM(1) AS personas_unicas
    FROM dbo.eventos_asistencia
    GROUP BY espacio_id, DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_aforo_biblioteca_bucket ON dbo.aforo_horario_biblioteca (bucket, espacio_id);

    EXEC('
    CREATE VIEW dbo.aforo_horario_estacionamiento WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        camara,
        DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS bucket,
        COUNT_BIG(*) AS count_rows,
        SUM(CASE WHEN direccion = ''entrada'' THEN 1 ELSE 0 END) AS entradas,
        SUM(CASE WHEN direccion = ''salida'' THEN 1 ELSE 0 END) AS salidas,
        SUM(CASE WHEN calidad_lectura = ''unknown'' THEN 1 ELSE 0 END) AS lecturas_fallidas
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, camara, DATEADD(hour, DATEDIFF(hour, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_aforo_estacionamiento_bucket ON dbo.aforo_horario_estacionamiento (bucket, espacio_id, camara);

    EXEC('
    CREATE VIEW dbo.vehiculos_diario_estacionamiento WITH SCHEMABINDING AS
    SELECT
        espacio_id,
        camara,
        direccion,
        DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126)) AS fecha_dia,
        COUNT_BIG(*) AS total_eventos
    FROM dbo.eventos_vehiculares
    GROUP BY espacio_id, camara, direccion, DATEADD(day, DATEDIFF(day, CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126), time), CONVERT(DATETIME2, ''2000-01-01T00:00:00'', 126));
    ');
    CREATE UNIQUE CLUSTERED INDEX UQ_vehiculos_diario_estacionamiento ON dbo.vehiculos_diario_estacionamiento (fecha_dia, espacio_id, camara, direccion);
    """)
