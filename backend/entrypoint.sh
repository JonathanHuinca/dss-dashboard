#!/bin/bash
set -e

echo "[entrypoint] Verificando conectividad con SQL Server..."
python - << 'EOF'
import sys, time, os, pyodbc
from app.core.config import settings

clave_sa = settings.MSSQL_SA_PASSWORD or os.environ.get("MSSQL_SA_PASSWORD")
host = "db"
puerto = 1433

for i in range(1, 25):
    try:
        conn = pyodbc.connect(
            f"DRIVER={{ODBC Driver 18 for SQL Server}};"
            f"SERVER={host},{puerto};"
            f"DATABASE=master;"
            f"UID=sa;"
            f"PWD={clave_sa};"
            f"TrustServerCertificate=yes;"
            f"Connection Timeout=5;",
            autocommit=True
        )
        conn.close()
        print(f"[entrypoint] SQL Server listo en el intento {i}.")
        sys.exit(0)
    except Exception as e:
        time.sleep(2)

print("[entrypoint] ERROR: Tiempo de espera agotado para conectar a SQL Server.")
sys.exit(1)
EOF

echo "[entrypoint] Inicializando base uct_dashboard y login uct_app bajo bloqueo aplicativo..."
python -c "from scripts.inicializar_base_datos import inicializar_base_y_permisos; inicializar_base_y_permisos()"

echo "[entrypoint] Ejecutando migraciones Alembic sobre uct_dashboard..."
alembic upgrade head

echo "[entrypoint] Iniciando servidor FastAPI..."
exec "$@"
