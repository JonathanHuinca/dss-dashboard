"""
sincronizar_snapshot_local.py — Exporta y restaura el snapshot completo de la base
de datos local (usuarios, dimensiones, eventos de asistencia/vehiculares, configuraciones)
y los modelos ML activos dentro de /app/seed_snapshot/snapshot_local.bin.gz.
"""
import argparse
import gzip
import os
import pickle
import sys
import time
from pathlib import Path

import pyodbc

RUTA_SNAPSHOT = Path(__file__).resolve().parents[1] / "seed_snapshot" / "snapshot_local.bin.gz"
DIRECTORIO_MODELOS = Path("/app/models") if Path("/app/models").exists() else Path(__file__).resolve().parents[1] / "models"

MODELOS_ACTIVOS = [
    "gbr_demand_biblioteca.joblib",
    "gbr_demand_biblioteca_metadata.json",
    "gbr_demand_vehicular.joblib",
    "gbr_demand_vehicular_metadata.json",
    "kmeans_parking.joblib",
    "kmeans_parking_metadata.json",
    "prophet_biblioteca_active.joblib",
    "prophet_biblioteca_sala1_active.joblib",
    "prophet_biblioteca_sala1_metadata.json",
    "prophet_biblioteca_sala2_active.joblib",
    "prophet_biblioteca_sala2_metadata.json",
    "prophet_biblioteca_todas_active.joblib",
    "prophet_biblioteca_todas_metadata.json",
    "prophet_vehicular_active.joblib",
    "prophet_vehicular_metadata.json",
]

TABLAS_EXCLUIDAS = {
    "alembic_version",
    "sysdiagrams",
}


def _conectar_sa(base_datos: str | None = None) -> pyodbc.Connection:
    from app.core.config import settings
    from sqlalchemy.engine.url import make_url
    if not base_datos:
        base_datos = make_url(settings.DATABASE_URL).database or "uct_dashboard"
    clave_sa = settings.MSSQL_SA_PASSWORD or os.environ.get("MSSQL_SA_PASSWORD")
    host = os.environ.get("DB_HOST", "db")
    puerto = int(os.environ.get("DB_PORT", "1433"))
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={host},{puerto};"
        f"DATABASE={base_datos};"
        f"UID=sa;"
        f"PWD={clave_sa};"
        f"TrustServerCertificate=yes;"
        f"Connection Timeout=15;"
    )
    return pyodbc.connect(conn_str, autocommit=False)


def exportar_snapshot() -> None:
    t0 = time.perf_counter()
    RUTA_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)

    conn = _conectar_sa("uct_dashboard")
    cur = conn.cursor()

    cur.execute(
        "SELECT name FROM sys.tables WHERE is_ms_shipped = 0 ORDER BY name"
    )
    tablas = [
        r[0] for r in cur.fetchall()
        if r[0] not in TABLAS_EXCLUIDAS and not r[0].startswith("queue_messages_")
    ]

    datos_tablas = {}
    total_filas = 0

    for tabla in tablas:
        cur.execute(
            """
            SELECT name, TYPE_NAME(system_type_id) AS tipo
            FROM sys.columns
            WHERE object_id = OBJECT_ID(?) AND is_computed = 0
            ORDER BY column_id
            """,
            (tabla,),
        )
        info_cols = cur.fetchall()
        columnas = [r[0] for r in info_cols]

        cur.execute(
            """
            SELECT 1
            FROM sys.columns
            FROM sys.columns
            WHERE object_id = OBJECT_ID(?) AND is_identity = 1
            """.replace("FROM sys.columns\n            FROM sys.columns", "FROM sys.columns"),
            (tabla,),
        )
        tiene_identidad = cur.fetchone() is not None

        exprs = []
        for col, tipo in info_cols:
            if tipo in ("datetimeoffset", "uniqueidentifier"):
                exprs.append(f"CAST([{col}] AS VARCHAR(50)) AS [{col}]")
            else:
                exprs.append(f"[{col}]")
        cols_sql = ", ".join(exprs)
        cur.execute(f"SELECT {cols_sql} FROM [{tabla}]")
        filas = [tuple(row) for row in cur.fetchall()]

        datos_tablas[tabla] = {
            "columns": columnas,
            "has_identity": tiene_identidad,
            "rows": filas,
        }
        total_filas += len(filas)
        print(f"  [exportar] {tabla}: {len(filas)} filas")

    conn.close()

    modelos_bytes = {}
    for nombre_archivo in MODELOS_ACTIVOS:
        ruta_m = DIRECTORIO_MODELOS / nombre_archivo
        if ruta_m.exists():
            modelos_bytes[nombre_archivo] = ruta_m.read_bytes()
            print(f"  [exportar-modelo] {nombre_archivo}: {len(modelos_bytes[nombre_archivo])} bytes")

    payload = {
        "tables": datos_tablas,
        "models": modelos_bytes,
    }

    with gzip.open(RUTA_SNAPSHOT, "wb", compresslevel=9) as gz:
        pickle.dump(payload, gz, protocol=pickle.HIGHEST_PROTOCOL)

    tamano_mb = RUTA_SNAPSHOT.stat().st_size / (1024 * 1024)
    duracion = time.perf_counter() - t0
    print(
        f"[snapshot] Exportacion completada en {duracion:.1f}s -> {RUTA_SNAPSHOT} "
        f"({tamano_mb:.2f} MB, {total_filas} filas totales, {len(modelos_bytes)} archivos de modelos)"
    )


TABLAS_HECHOS_MASIVOS = {
    "eventos_asistencia",
    "eventos_vehiculares",
}


def restaurar_snapshot(
    base_datos: str | None = None,
    forzar: bool = False,
    modo: str = "completo",
) -> None:
    if not RUTA_SNAPSHOT.exists():
        print(f"[snapshot] No existe {RUTA_SNAPSHOT}; se omite restauracion.")
        return

    t0 = time.perf_counter()
    with gzip.open(RUTA_SNAPSHOT, "rb") as gz:
        payload = pickle.load(gz)

    # 1. Restaurar modelos ML activos en /app/models
    if modo in ("completo", "base"):
        modelos_bytes = payload.get("models", {})
        if modelos_bytes:
            try:
                DIRECTORIO_MODELOS.mkdir(parents=True, exist_ok=True)
                for nombre_archivo, contenido in modelos_bytes.items():
                    destino = DIRECTORIO_MODELOS / nombre_archivo
                    if forzar or not destino.exists():
                        destino.write_bytes(contenido)
                        print(f"  [snapshot-modelo] Restaurado {nombre_archivo}")
            except Exception as e:
                print(f"  [snapshot-modelo] Advertencia al restaurar modelos: {e}")

    conn = _conectar_sa(base_datos)
    cur = conn.cursor()

    datos_tablas_todas = payload.get("tables", {})
    if modo == "base":
        datos_tablas = {
            k: v for k, v in datos_tablas_todas.items() if k not in TABLAS_HECHOS_MASIVOS
        }
    elif modo == "hechos":
        datos_tablas = {
            k: v for k, v in datos_tablas_todas.items() if k in TABLAS_HECHOS_MASIVOS
        }
    else:
        datos_tablas = datos_tablas_todas

    if not forzar:
        try:
            if modo == "base":
                cur.execute("SELECT COUNT(*) FROM [usuarios] WHERE email = 'jhuinca2020@alu.uct.cl'")
                tiene_usuario = cur.fetchone()[0] > 0
                cur.execute("SELECT COUNT(*) FROM [dim_estudiante_carrera]")
                conteo_dim = cur.fetchone()[0]
                if tiene_usuario and conteo_dim >= 4000:
                    print("[snapshot] Tablas base y usuarios locales ya sincronizados. Se omite.")
                    conn.close()
                    return
            elif modo == "hechos":
                cur.execute("SELECT COUNT(*) FROM [eventos_asistencia]")
                conteo_asist = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM [eventos_vehiculares]")
                conteo_veh = cur.fetchone()[0]
                if conteo_asist >= 130000 and conteo_veh >= 45000:
                    print(
                        f"[snapshot] Tablas de hechos ya sincronizadas "
                        f"({conteo_asist} asistencia, {conteo_veh} vehiculares). Se omite."
                    )
                    conn.close()
                    return
            else:
                cur.execute("SELECT COUNT(*) FROM [eventos_asistencia]")
                conteo_asistencia = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM [usuarios] WHERE email = 'jhuinca2020@alu.uct.cl'")
                tiene_usuario_local = cur.fetchone()[0] > 0
                if conteo_asistencia >= 130000 and tiene_usuario_local:
                    print("[snapshot] Base completa ya sincronizada. Se omite.")
                    conn.close()
                    return
        except Exception:
            pass

    print(f"[snapshot] Iniciando restauracion (modo={modo}) en '{base_datos or 'uct_dashboard'}'...")

    cur.execute("SELECT name FROM sys.tables WHERE is_ms_shipped = 0")
    tablas_existentes = {r[0] for r in cur.fetchall()}

    for tabla in datos_tablas:
        if tabla in tablas_existentes:
            cur.execute(f"ALTER TABLE [{tabla}] NOCHECK CONSTRAINT ALL")
    conn.commit()

    try:
        for tabla in datos_tablas:
            if tabla in tablas_existentes:
                cur.execute(f"DELETE FROM [{tabla}]")
        conn.commit()

        LOTE = 2500
        for tabla, meta in datos_tablas.items():
            if tabla not in tablas_existentes:
                continue
            filas = meta["rows"]
            if not filas:
                continue

            t_tabla = time.perf_counter()
            columnas_snap = meta["columns"]
            cur.execute(
                """
                SELECT name
                FROM sys.columns
                WHERE object_id = OBJECT_ID(?) AND is_computed = 0
                """,
                (tabla,),
            )
            columnas_db = {r[0] for r in cur.fetchall()}

            indices_validos = [i for i, c in enumerate(columnas_snap) if c in columnas_db]
            columnas_finales = [columnas_snap[i] for i in indices_validos]
            if not columnas_finales:
                continue

            tiene_id = meta["has_identity"]
            cols_sql = ", ".join(f"[{c}]" for c in columnas_finales)
            placeholders = ", ".join("?" for _ in columnas_finales)
            sql_insert = f"INSERT INTO [{tabla}] ({cols_sql}) VALUES ({placeholders})"

            if tiene_id:
                cur.execute(f"SET IDENTITY_INSERT [{tabla}] ON")

            cur.fast_executemany = len(filas) >= 500

            try:
                for inicio in range(0, len(filas), LOTE):
                    sub = filas[inicio : inicio + LOTE]
                    if len(indices_validos) != len(columnas_snap):
                        sub = [tuple(r[i] for i in indices_validos) for r in sub]
                    cur.executemany(sql_insert, sub)
                    conn.commit()
            finally:
                if tiene_id:
                    cur.execute(f"SET IDENTITY_INSERT [{tabla}] OFF")
                    conn.commit()

            dt_tabla = time.perf_counter() - t_tabla
            print(f"  [snapshot-db] {tabla}: {len(filas)} filas restauradas ({dt_tabla:.1f}s)")
    finally:
        for tabla in datos_tablas:
            if tabla in tablas_existentes:
                cur.execute(f"ALTER TABLE [{tabla}] CHECK CONSTRAINT ALL")
        conn.commit()
        conn.close()

    duracion = time.perf_counter() - t0
    print(f"[snapshot] Restauracion (modo={modo}) completada exitosamente en {duracion:.1f}s.")


def probar_restauracion_en_limpio() -> None:
    import subprocess
    from app.core.config import settings
    from sqlalchemy.engine.url import make_url

    db_actual = make_url(settings.DATABASE_URL).database or "uct_dashboard"
    db_test = "uct_test_restore"

    conn = _conectar_sa("master")
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        f"IF DB_ID('{db_test}') IS NOT NULL BEGIN "
        f"ALTER DATABASE [{db_test}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
        f"DROP DATABASE [{db_test}]; END; "
        f"CREATE DATABASE [{db_test}];"
    )
    conn.close()

    try:
        from urllib.parse import quote_plus
        clave_sa = settings.MSSQL_SA_PASSWORD or os.environ.get("MSSQL_SA_PASSWORD")
        env = os.environ.copy()
        env["DATABASE_URL_SYNC"] = (
            f"mssql+pyodbc://sa:{clave_sa}@db:1433/{db_test}"
            "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
        )
        subprocess.run(["alembic", "upgrade", "head"], env=env, check=True)
        restaurar_snapshot(base_datos=db_test, forzar=True, modo="base")
    finally:
        conn = _conectar_sa("master")
        conn.autocommit = True
        conn.cursor().execute(
            f"ALTER DATABASE [{db_test}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE; "
            f"DROP DATABASE [{db_test}];"
        )
        conn.close()
    print("[snapshot] PRUEBA DE RESTAURACION EN LIMPIO EXITOSA")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    parser = argparse.ArgumentParser()
    parser.add_argument("--exportar", action="store_true")
    parser.add_argument("--restaurar", action="store_true")
    parser.add_argument("--restaurar-base", action="store_true")
    parser.add_argument("--restaurar-hechos", action="store_true")
    parser.add_argument("--probar", action="store_true")
    parser.add_argument("--forzar", action="store_true")
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    if args.exportar:
        exportar_snapshot()
    elif args.restaurar:
        restaurar_snapshot(base_datos=args.db, forzar=args.forzar, modo="completo")
    elif args.restaurar_base:
        restaurar_snapshot(base_datos=args.db, forzar=args.forzar, modo="base")
    elif args.restaurar_hechos:
        restaurar_snapshot(base_datos=args.db, forzar=args.forzar, modo="hechos")
    elif args.probar:
        probar_restauracion_en_limpio()
    else:
        parser.print_help()
