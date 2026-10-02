-- ============================================================
-- Script de referencia SQL completo — UCT Dashboard
-- Generado para TimescaleDB (PostgreSQL 16)
-- NOTA: La migración Alembic 001_initial_schema.py es la
--       fuente autoritativa. Este archivo es solo lectura/referencia.
-- ============================================================

-- 0. Extensión
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- 1. Usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    email         VARCHAR(120) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol           VARCHAR(30)  NOT NULL
                  CHECK (rol IN ('administrador', 'operador', 'directivo')),
    activo        BOOLEAN DEFAULT TRUE,
    creado_en     TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Espacios
CREATE TABLE IF NOT EXISTS espacios (
    id            SERIAL PRIMARY KEY,
    campus        VARCHAR(80)  NOT NULL,
    tipo          VARCHAR(30)  NOT NULL
                  CHECK (tipo IN ('biblioteca', 'estacionamiento')),
    nombre        VARCHAR(120) NOT NULL,
    capacidad_max INTEGER NOT NULL CHECK (capacidad_max > 0),
    activo        BOOLEAN DEFAULT TRUE
);

-- 3. Hipertabla: eventos_asistencia
CREATE TABLE IF NOT EXISTS eventos_asistencia (
    time                    TIMESTAMPTZ  NOT NULL,
    espacio_id              INTEGER      NOT NULL REFERENCES espacios(id),
    person_id_hash          VARCHAR(64)  NOT NULL,
    door_entrada            VARCHAR(80),
    door_salida             VARCHAR(80),
    primera_entrada         TIMESTAMPTZ  NOT NULL,
    ultima_salida           TIMESTAMPTZ,
    salida_imputada         BOOLEAN      DEFAULT FALSE,
    permanencia_min         NUMERIC(8,2),
    marcajes_totales        SMALLINT     DEFAULT 1,
    alerta_coherencia_fechas BOOLEAN     DEFAULT FALSE,
    alerta_marcajes         BOOLEAN      DEFAULT FALSE
);

SELECT create_hypertable(
    'eventos_asistencia', 'time',
    chunk_time_interval => INTERVAL '1 week'
);

CREATE INDEX ix_ea_espacio_time ON eventos_asistencia (espacio_id, time DESC);
CREATE INDEX ix_ea_person_time  ON eventos_asistencia (person_id_hash, time DESC);

ALTER TABLE eventos_asistencia SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'espacio_id',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('eventos_asistencia', INTERVAL '1 month');
SELECT add_retention_policy('eventos_asistencia',   INTERVAL '24 months');

-- 4. Hipertabla: eventos_vehiculares
CREATE TABLE IF NOT EXISTS eventos_vehiculares (
    time            TIMESTAMPTZ NOT NULL,
    espacio_id      INTEGER     NOT NULL REFERENCES espacios(id),
    patente_hash    VARCHAR(64) NOT NULL,
    camara          VARCHAR(80) NOT NULL,
    direccion       VARCHAR(10) NOT NULL CHECK (direccion IN ('entrada', 'salida')),
    tipo_vehiculo   VARCHAR(40),
    marca           VARCHAR(60),
    color           VARCHAR(40),
    calidad_lectura VARCHAR(10) DEFAULT 'ok'
                    CHECK (calidad_lectura IN ('ok', 'unknown', 'baja'))
);

SELECT create_hypertable(
    'eventos_vehiculares', 'time',
    chunk_time_interval => INTERVAL '1 week'
);

CREATE INDEX ix_ev_espacio_time ON eventos_vehiculares (espacio_id, time DESC);
CREATE INDEX ix_ev_patente_time ON eventos_vehiculares (patente_hash, time DESC);

ALTER TABLE eventos_vehiculares SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'espacio_id, camara',
    timescaledb.compress_orderby   = 'time DESC'
);
SELECT add_compression_policy('eventos_vehiculares', INTERVAL '1 month');
SELECT add_retention_policy('eventos_vehiculares',   INTERVAL '24 months');

-- 5. Calendario Académico
CREATE TABLE IF NOT EXISTS calendario_academico (
    fecha                  DATE PRIMARY KEY,
    is_holiday             BOOLEAN DEFAULT FALSE,
    is_break               BOOLEAN DEFAULT FALSE,
    is_exam_period         BOOLEAN DEFAULT FALSE,
    is_class_milestone     BOOLEAN DEFAULT FALSE,
    suspension_actividades BOOLEAN DEFAULT FALSE,
    descripcion            TEXT,
    fuente                 VARCHAR(50) DEFAULT 'scraping'
);

-- 6. Jobs de Ingesta
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(255) NOT NULL,
    tipo            VARCHAR(20)  NOT NULL CHECK (tipo IN ('asistencia', 'vehicular', 'academico')),
    estado          VARCHAR(20)  NOT NULL DEFAULT 'queued'
                    CHECK (estado IN ('queued', 'processing', 'completed', 'failed')),
    registros_ok    INTEGER      DEFAULT 0,
    registros_error INTEGER      DEFAULT 0,
    error_detail    TEXT,
    creado_por      INTEGER      REFERENCES usuarios(id),
    creado_en       TIMESTAMPTZ  DEFAULT NOW(),
    completado_en   TIMESTAMPTZ
);

-- 7. Rollup Histórico (> 24 meses)
CREATE TABLE IF NOT EXISTS rollup_historico_diario (
    fecha                   DATE    NOT NULL,
    espacio_id              INTEGER NOT NULL REFERENCES espacios(id),
    tipo                    VARCHAR(20) NOT NULL,
    ingresos_total          INTEGER NOT NULL,
    salidas_total           INTEGER NOT NULL,
    personas_unicas         INTEGER,
    permanencia_mediana_min NUMERIC(8,2),
    PRIMARY KEY (fecha, espacio_id, tipo)
);

-- 8. Continuous Aggregate: aforo_horario_biblioteca
CREATE MATERIALIZED VIEW aforo_horario_biblioteca
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)                                         AS bucket,
    espacio_id,
    COUNT(*)                                                            AS ingresos,
    COUNT(*) FILTER (WHERE ultima_salida IS NOT NULL OR salida_imputada) AS salidas,
    COUNT(DISTINCT person_id_hash)                                      AS personas_unicas,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY permanencia_min)        AS permanencia_mediana_min
FROM eventos_asistencia
WHERE alerta_coherencia_fechas = FALSE
GROUP BY bucket, espacio_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy('aforo_horario_biblioteca',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '30 minutes',
    schedule_interval => INTERVAL '30 minutes'
);

-- 9. Continuous Aggregate: aforo_horario_estacionamiento
CREATE MATERIALIZED VIEW aforo_horario_estacionamiento
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)                                         AS bucket,
    espacio_id,
    camara,
    COUNT(*) FILTER (WHERE direccion = 'entrada')                       AS entradas,
    COUNT(*) FILTER (WHERE direccion = 'salida')                        AS salidas,
    COUNT(*) FILTER (WHERE calidad_lectura = 'unknown')                 AS lecturas_fallidas
FROM eventos_vehiculares
GROUP BY bucket, espacio_id, camara
WITH NO DATA;

SELECT add_continuous_aggregate_policy('aforo_horario_estacionamiento',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '30 minutes',
    schedule_interval => INTERVAL '30 minutes'
);

-- 10. Seed: espacios CSF
INSERT INTO espacios (campus, tipo, nombre, capacidad_max) VALUES
('CSF', 'biblioteca',      'Biblioteca Campus San Francisco',      350),
('CSF', 'estacionamiento', 'Estacionamiento Campus San Francisco', 180)
ON CONFLICT DO NOTHING;
