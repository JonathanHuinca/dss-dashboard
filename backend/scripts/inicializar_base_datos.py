"""
inicializar_base_datos.py — Inicialización DevSecOps de Base de Datos y Login con Permisos Mínimos.

Crea la base de datos uct_dashboard y el login uct_app con roles de mínimo privilegio
(db_datareader, db_datawriter, db_ddladmin). Migra automáticamente tablas y datos
preexistentes desde master hacia uct_dashboard bajo bloqueo exclusivo para evitar colisiones.
"""

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Asegurar path de la app
directorio_raiz = Path(__file__).resolve().parent.parent
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

import pyodbc
from app.core.config import settings

TABLAS_ORDEN_MIGRACION = [
    "roles",
    "espacios",
    "usuarios",
    "usuarios_roles",
    "configuracion_espacios",
    "horarios_operacion",
    "salas_biblioteca",
    "sectores_estacionamiento",
    "dim_carrera_programa",
    "dim_estudiante_carrera",
    "calendario_academico",
    "estado_calendario_anual",
    "estado_sincronizacion_fuente",
    "contingencias_academicas",
    "tokens_activacion",
    "ingestion_jobs",
    "eventos_asistencia",
    "eventos_vehiculares",
    "chat_audit_logs",
    "download_audit_logs",
    "chat_conversaciones",
    "chat_mensajes",
    "ejecuciones_tareas",
    "rollup_historico_diario",
    "alembic_version",
]


def extraer_host_puerto_bd() -> tuple[str, int]:
    """Extrae el host y puerto de la cadena DATABASE_URL configurada."""
    url = settings.DATABASE_URL
    if "@" in url:
        parte_host = url.split("@")[1].split("/")[0]
        if ":" in parte_host:
            host, puerto = parte_host.split(":")
            return host, int(puerto)
        return parte_host, 1433
    return "db", 1433


def obtener_conexion_sa(host: str, puerto: int, clave_sa: str, base_datos: str = "master") -> pyodbc.Connection:
    """Establece conexión administrativa mediante el usuario sa hacia SQL Server."""
    cadena_conexion = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={host},{puerto};"
        f"DATABASE={base_datos};"
        f"UID=sa;"
        f"PWD={clave_sa};"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=30;"
    )
    return pyodbc.connect(cadena_conexion, autocommit=True)


def inicializar_base_y_permisos():
    """Ejecuta la creación de base de datos uct_dashboard y login uct_app bajo bloqueo aplicativo."""
    clave_sa = settings.MSSQL_SA_PASSWORD or os.environ.get("MSSQL_SA_PASSWORD")
    if not clave_sa:
        print("[inicializar_bd] ADVERTENCIA: MSSQL_SA_PASSWORD no configurada. Omitiendo aprovisionamiento sa.")
        return

    usuario_app = settings.MSSQL_USUARIO_APP or "uct_app"
    clave_app = settings.MSSQL_CLAVE_APP or os.environ.get("MSSQL_CLAVE_APP")
    if not clave_app:
        print("[inicializar_bd] ERROR: MSSQL_CLAVE_APP no configurada.")
        sys.exit(1)

    host, puerto = extraer_host_puerto_bd()
    print(f"[inicializar_bd] Conectando como sa a SQL Server en {host}:{puerto}...")

    # Reintentos de conexión por si el contenedor SQL Server aún está iniciando
    conn = None
    for intento in range(1, 11):
        try:
            conn = obtener_conexion_sa(host, puerto, clave_sa, "master")
            break
        except Exception as e:
            print(f"[inicializar_bd] Esperando disponibilidad de SQL Server (intento {intento}/10): {e}")
            time.sleep(3)

    if not conn:
        print("[inicializar_bd] ERROR: No fue posible conectar con SQL Server como sa.")
        sys.exit(1)

    cursor = conn.cursor()

    try:
        # 1. Adquirir bloqueo exclusivo aplicativo (sp_getapplock)
        print("[inicializar_bd] Adquiriendo bloqueo exclusivo de inicialización...")
        cursor.execute(
            """
            DECLARE @res INT;
            EXEC @res = sp_getapplock @Resource = 'uct_inicializar_bd', @LockMode = 'Exclusive', @LockOwner = 'Session', @LockTimeout = 60000;
            SELECT @res;
            """
        )
        lock_res = cursor.fetchone()[0]
        if lock_res < 0:
            print(f"[inicializar_bd] No se pudo obtener el bloqueo exclusivo (código {lock_res}).")
            return

        # 2. Crear base de datos uct_dashboard si no existe
        cursor.execute("SELECT name FROM sys.databases WHERE name = 'uct_dashboard'")
        base_existe = cursor.fetchone() is not None

        if not base_existe:
            print("[inicializar_bd] Creando base de datos 'uct_dashboard'...")
            cursor.execute("CREATE DATABASE [uct_dashboard];")
            print("[inicializar_bd] Base de datos 'uct_dashboard' creada exitosamente.")
        else:
            print("[inicializar_bd] Base de datos 'uct_dashboard' ya existe.")

        # 3. Crear o actualizar login a nivel de servidor uct_app
        cursor.execute(f"SELECT name FROM sys.server_principals WHERE name = '{usuario_app}'")
        login_existe = cursor.fetchone() is not None

        clave_sql_escapada = clave_app.replace("'", "''")
        if not login_existe:
            print(f"[inicializar_bd] Creando login a nivel de servidor '{usuario_app}'...")
            cursor.execute(f"CREATE LOGIN [{usuario_app}] WITH PASSWORD = '{clave_sql_escapada}', CHECK_POLICY = OFF;")
        else:
            print(f"[inicializar_bd] Actualizando contraseña de login '{usuario_app}'...")
            cursor.execute(f"ALTER LOGIN [{usuario_app}] WITH PASSWORD = '{clave_sql_escapada}';")

        # 4. Configurar usuario y roles mínimos en la base de datos uct_dashboard
        conn_uct = obtener_conexion_sa(host, puerto, clave_sa, "uct_dashboard")
        cursor_uct = conn_uct.cursor()

        cursor_uct.execute(f"SELECT name FROM sys.database_principals WHERE name = '{usuario_app}'")
        user_db_existe = cursor_uct.fetchone() is not None

        if not user_db_existe:
            print(f"[inicializar_bd] Creando usuario de base de datos '{usuario_app}' en 'uct_dashboard'...")
            cursor_uct.execute(f"CREATE USER [{usuario_app}] FOR LOGIN [{usuario_app}];")

        # Asignar roles mínimos para operación y DDL de Alembic
        print(f"[inicializar_bd] Asignando roles de mínimo privilegio a '{usuario_app}'...")
        cursor_uct.execute(f"ALTER ROLE [db_datareader] ADD MEMBER [{usuario_app}];")
        cursor_uct.execute(f"ALTER ROLE [db_datawriter] ADD MEMBER [{usuario_app}];")
        cursor_uct.execute(f"ALTER ROLE [db_ddladmin] ADD MEMBER [{usuario_app}];")

        # 5. Ejecutar migraciones Alembic sobre uct_dashboard para crear esquema si es necesario
        print("[inicializar_bd] Verificando esquema y ejecutando Alembic upgrade head en uct_dashboard...")
        os.environ["DATABASE_URL"] = (
            f"mssql+aioodbc://sa:{clave_sa}@{host}:{puerto}/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )
        os.environ["DATABASE_URL_SYNC"] = (
            f"mssql+pyodbc://sa:{clave_sa}@{host}:{puerto}/uct_dashboard?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )

        try:
            from alembic import command
            from alembic.config import Config
            ruta_alembic_ini = str(directorio_raiz / "alembic.ini")
            cfg = Config(ruta_alembic_ini)
            cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL_SYNC"])
            command.upgrade(cfg, "head")
            print("[inicializar_bd] Migraciones Alembic aplicadas exitosamente sobre uct_dashboard.")
        except Exception as error_alembic:
            print(f"[inicializar_bd] Advertencia durante Alembic upgrade: {error_alembic}")

        print("[inicializar_bd] Verificando tablas para sincronización desde master...")
        try:
            cursor_uct.execute("EXEC sp_MSforeachtable 'ALTER TABLE ? NOCHECK CONSTRAINT ALL';")
        except Exception:
            pass

        for tabla in TABLAS_ORDEN_MIGRACION:
            tiene_identity = False
            try:
                cursor.execute(f"SELECT COUNT(*) FROM master.INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{tabla}'")
                if cursor.fetchone()[0] == 0:
                    continue

                cursor_uct.execute(f"SELECT COUNT(*) FROM uct_dashboard.INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = '{tabla}'")
                if cursor_uct.fetchone()[0] == 0:
                    continue

                cursor.execute(f"SELECT COUNT(*) FROM master.dbo.[{tabla}]")
                filas_master = cursor.fetchone()[0]
                if filas_master == 0:
                    continue

                cursor_uct.execute(f"SELECT COUNT(*) FROM uct_dashboard.dbo.[{tabla}]")
                filas_uct = cursor_uct.fetchone()[0]
                if filas_uct > 0:
                    continue

                # Obtener columnas comunes entre ambas bases
                cursor.execute(f"SELECT COLUMN_NAME FROM master.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{tabla}'")
                cols_master = set(row[0] for row in cursor.fetchall())
                cursor_uct.execute(f"SELECT COLUMN_NAME FROM uct_dashboard.INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '{tabla}'")
                cols_uct = set(row[0] for row in cursor_uct.fetchall())
                cols_comunes = [c for c in cols_master if c in cols_uct]

                if not cols_comunes:
                    continue

                cols_str = ", ".join([f"[{c}]" for c in cols_comunes])

                # Verificar si tiene columna IDENTITY
                cursor_uct.execute(f"SELECT 1 FROM sys.columns WHERE object_id = OBJECT_ID('uct_dashboard.dbo.[{tabla}]') AND is_identity = 1")
                tiene_identity = cursor_uct.fetchone() is not None

                if tiene_identity:
                    cursor_uct.execute(f"SET IDENTITY_INSERT uct_dashboard.dbo.[{tabla}] ON;")

                cursor_uct.execute(
                    f"INSERT INTO uct_dashboard.dbo.[{tabla}] ({cols_str}) SELECT {cols_str} FROM master.dbo.[{tabla}];"
                )
                print(f"  [migrado] {tabla}: {filas_master} filas transferidas.")
            except Exception as error_migracion_tabla:
                print(f"  [error migrando {tabla}]: {error_migracion_tabla}")
            finally:
                if tiene_identity:
                    try:
                        cursor_uct.execute(f"SET IDENTITY_INSERT uct_dashboard.dbo.[{tabla}] OFF;")
                    except Exception:
                        pass

        print("[inicializar_bd] Reactivando restricciones de integridad en uct_dashboard...")
        try:
            cursor_uct.execute("EXEC sp_MSforeachtable 'ALTER TABLE ? WITH CHECK CHECK CONSTRAINT ALL';")
        except Exception:
            pass

        # 7. Liberar bloqueo exclusivo aplicativo
        cursor.execute("EXEC sp_releaseapplock @Resource = 'uct_inicializar_bd', @LockOwner = 'Session';")
        print("[inicializar_bd] Inicialización finalizada exitosamente con login 'uct_app' y base 'uct_dashboard'.")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    inicializar_base_y_permisos()
