"""Initial schema: hipertablas TimescaleDB, continuous aggregates y seed de espacios CSF

Revision ID: 001
Revises:
Create Date: 2026-09-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 0. Extensiones
    # -------------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

    # -------------------------------------------------------------------------
    # 1. Tablas relacionales base
    # -------------------------------------------------------------------------
    op.create_table(
        "usuarios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False),
        sa.Column("email", sa.String(120), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("rol", sa.String(30), nullable=False),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "rol IN ('administrador', 'operador', 'directivo')", name="ck_usuarios_rol"
        ),
    )

    op.create_table(
        "espacios",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("campus", sa.String(80), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("capacidad_max", sa.Integer, nullable=False),
        sa.Column("activo", sa.Boolean, server_default="true"),
        sa.CheckConstraint(
            "tipo IN ('biblioteca', 'estacionamiento')", name="ck_espacios_tipo"
        ),
        sa.CheckConstraint("capacidad_max > 0", name="ck_espacios_capacidad"),
    )

    op.create_table(
        "calendario_academico",
        sa.Column("fecha", sa.Date, primary_key=True),
        sa.Column("is_holiday", sa.Boolean, server_default="false"),
        sa.Column("is_break", sa.Boolean, server_default="false"),
        sa.Column("is_exam_period", sa.Boolean, server_default="false"),
        sa.Column("is_class_milestone", sa.Boolean, server_default="false"),
        sa.Column("suspension_actividades", sa.Boolean, server_default="false"),
        sa.Column("descripcion", sa.Text),
        sa.Column("fuente", sa.String(50), server_default="'scraping'"),
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("estado", sa.String(20), nullable=False, server_default="'queued'"),
        sa.Column("registros_ok", sa.Integer, server_default="0"),
        sa.Column("registros_error", sa.Integer, server_default="0"),
        sa.Column("error_detail", sa.Text),
        sa.Column("creado_por", sa.Integer, sa.ForeignKey("usuarios.id")),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completado_en", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "tipo IN ('asistencia', 'vehicular', 'academico')", name="ck_ij_tipo"
        ),
        sa.CheckConstraint(
            "estado IN ('queued', 'processing', 'completed', 'failed')", name="ck_ij_estado"
        ),
    )

    op.create_table(
        "rollup_historico_diario",
        sa.Column("fecha", sa.Date, nullable=False, primary_key=True),
        sa.Column(
            "espacio_id",
            sa.Integer,
            sa.ForeignKey("espacios.id"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column("tipo", sa.String(20), nullable=False, primary_key=True),
        sa.Column("ingresos_total", sa.Integer, nullable=False),
        sa.Column("salidas_total", sa.Integer, nullable=False),
        sa.Column("personas_unicas", sa.Integer),
        sa.Column("permanencia_mediana_min", sa.Numeric(8, 2)),
    )

    # -------------------------------------------------------------------------
    # 2. Hipertabla: eventos_asistencia
    # -------------------------------------------------------------------------
    op.create_table(
        "eventos_asistencia",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("espacio_id", sa.Integer, sa.ForeignKey("espacios.id"), nullable=False),
        sa.Column("person_id_hash", sa.String(64), nullable=False),
        sa.Column("door_entrada", sa.String(80)),
        sa.Column("door_salida", sa.String(80)),
        sa.Column("primera_entrada", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultima_salida", sa.DateTime(timezone=True)),
        sa.Column("salida_imputada", sa.Boolean, server_default="false"),
        sa.Column("permanencia_min", sa.Numeric(8, 2)),
        sa.Column("marcajes_totales", sa.SmallInteger, server_default="1"),
        sa.Column("alerta_coherencia_fechas", sa.Boolean, server_default="false"),
        sa.Column("alerta_marcajes", sa.Boolean, server_default="false"),
    )
    op.execute(
        "SELECT create_hypertable('eventos_asistencia', 'time', "
        "chunk_time_interval => INTERVAL '1 week');"
    )
    op.create_index("ix_ea_espacio_time", "eventos_asistencia", ["espacio_id", "time"])
    op.create_index("ix_ea_person_time",  "eventos_asistencia", ["person_id_hash", "time"])

    op.execute("""
        ALTER TABLE eventos_asistencia SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'espacio_id',
            timescaledb.compress_orderby   = 'time DESC'
        );
    """)
    op.execute(
        "SELECT add_compression_policy('eventos_asistencia', INTERVAL '1 month');"
    )
    op.execute(
        "SELECT add_retention_policy('eventos_asistencia', INTERVAL '24 months');"
    )

    # -------------------------------------------------------------------------
    # 3. Hipertabla: eventos_vehiculares
    # -------------------------------------------------------------------------
    op.create_table(
        "eventos_vehiculares",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("espacio_id", sa.Integer, sa.ForeignKey("espacios.id"), nullable=False),
        sa.Column("patente_hash", sa.String(64), nullable=False),
        sa.Column("camara", sa.String(80), nullable=False),
        sa.Column("direccion", sa.String(10), nullable=False),
        sa.Column("tipo_vehiculo", sa.String(40)),
        sa.Column("marca", sa.String(60)),
        sa.Column("color", sa.String(40)),
        sa.Column("calidad_lectura", sa.String(10), server_default="'ok'"),
        sa.CheckConstraint("direccion IN ('entrada', 'salida')", name="ck_ev_direccion"),
        sa.CheckConstraint(
            "calidad_lectura IN ('ok', 'unknown', 'baja')", name="ck_ev_calidad"
        ),
    )
    op.execute(
        "SELECT create_hypertable('eventos_vehiculares', 'time', "
        "chunk_time_interval => INTERVAL '1 week');"
    )
    op.create_index("ix_ev_espacio_time",  "eventos_vehiculares", ["espacio_id", "time"])
    op.create_index("ix_ev_patente_time",  "eventos_vehiculares", ["patente_hash", "time"])

    op.execute("""
        ALTER TABLE eventos_vehiculares SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'espacio_id, camara',
            timescaledb.compress_orderby   = 'time DESC'
        );
    """)
    op.execute(
        "SELECT add_compression_policy('eventos_vehiculares', INTERVAL '1 month');"
    )
    op.execute(
        "SELECT add_retention_policy('eventos_vehiculares', INTERVAL '24 months');"
    )

    # -------------------------------------------------------------------------
    # 4. Continuous Aggregate: aforo_horario_biblioteca
    # -------------------------------------------------------------------------
    op.execute("""
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
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('aforo_horario_biblioteca',
            start_offset      => INTERVAL '3 hours',
            end_offset        => INTERVAL '30 minutes',
            schedule_interval => INTERVAL '30 minutes'
        );
    """)

    # -------------------------------------------------------------------------
    # 5. Continuous Aggregate: aforo_horario_estacionamiento
    # -------------------------------------------------------------------------
    op.execute("""
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
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy('aforo_horario_estacionamiento',
            start_offset      => INTERVAL '3 hours',
            end_offset        => INTERVAL '30 minutes',
            schedule_interval => INTERVAL '30 minutes'
        );
    """)

    # -------------------------------------------------------------------------
    # 6. Seed: Espacios del Campus San Francisco (CSF)
    # -------------------------------------------------------------------------
    op.execute("""
        INSERT INTO espacios (campus, tipo, nombre, capacidad_max) VALUES
        ('CSF', 'biblioteca',      'Biblioteca Campus San Francisco',     350),
        ('CSF', 'estacionamiento', 'Estacionamiento Campus San Francisco', 180);
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aforo_horario_estacionamiento CASCADE;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS aforo_horario_biblioteca CASCADE;")
    op.drop_table("eventos_vehiculares")
    op.drop_table("eventos_asistencia")
    op.drop_table("rollup_historico_diario")
    op.drop_table("ingestion_jobs")
    op.drop_table("calendario_academico")
    op.drop_table("espacios")
    op.drop_table("usuarios")
