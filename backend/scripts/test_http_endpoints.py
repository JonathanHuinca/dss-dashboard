"""
test_http_endpoints.py — Prueba de integración HTTP directa sobre los endpoints
POST /api/v1/ingestion/validate y POST /api/v1/ingestion/process.
"""
import asyncio
import httpx
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token


async def main():
    # 1. Limpieza inicial
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM eventos_asistencia WHERE time >= '2026-05-15 00:00:00' AND time <= '2026-05-15 23:59:59'"))
        await s.execute(text("DELETE FROM ingestion_jobs WHERE filename = 'test_http.csv'"))
        await s.commit()

    token = create_access_token(user_id=1, rol="SuperAdmin")
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "http://localhost:8000/api/v1/ingestion"

    csv_data = (
        "Fecha,Primera entrada,Ultima salida,Door de entrada,Door de salida,Numero de matricula,Marcajes\n"
        "2026-05-15,08:00:00,12:00:00,Acceso Norte,Acceso Norte,2024100999,1\n"
    ).encode("utf-8")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # 2. Test /validate
        files = {"file": ("test_http.csv", csv_data, "text/csv")}
        params = {"tipo": "asistencia", "espacio_id": 1}
        r_val = await client.post(f"{base_url}/validate", headers=headers, params=params, files=files)
        print("HTTP /validate Status:", r_val.status_code)
        assert r_val.status_code == 200
        val_json = r_val.json()
        assert val_json["total_filas"] == 1
        assert val_json["clave_enlace_detectada"] == "matricula"

        # 3. Test /process en modo tolerante
        files2 = {"file": ("test_http.csv", csv_data, "text/csv")}
        params2 = {
            "tipo": "asistencia",
            "espacio_id": 1,
            "modo_solapamiento": "merge",
            "clave_enlace": "matricula",
            "modo_enlace": "tolerante",
        }
        r_proc = await client.post(f"{base_url}/process", headers=headers, params=params2, files=files2)
        print("HTTP /process Status:", r_proc.status_code)
        assert r_proc.status_code == 200
        proc_json = r_proc.json()
        assert proc_json["status"] == "completed"
        assert proc_json["registros_insertados"] == 1
        assert proc_json["carreras_no_catalogadas"] == 1

        print("PRUEBAS HTTP FINALIZADAS CON ÉXITO TOTAL.")

    # 4. Limpieza final
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM eventos_asistencia WHERE time >= '2026-05-15 00:00:00' AND time <= '2026-05-15 23:59:59'"))
        await s.execute(text("DELETE FROM ingestion_jobs WHERE filename = 'test_http.csv'"))
        await s.commit()


if __name__ == "__main__":
    asyncio.run(main())
