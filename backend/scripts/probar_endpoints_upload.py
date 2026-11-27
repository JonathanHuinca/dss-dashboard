"""
probar_endpoints_upload.py — Pruebas de API REST para POST /ingestion/upload y GET /ingestion/{job_id}/status.
"""
import asyncio
import io
import sys
import uuid

sys.path.insert(0, "/app")

from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.auth_service import create_access_token


async def test_endpoints():
    token = create_access_token(
        user_id=1,
        rol="Admin_Sistema",
        roles=["Admin_Sistema"],
        can_ingest=True,
    )
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Probar extensión no permitida
        print("1. Probando rechazo de extensión inválida (.txt)...")
        files_invalid = {"file": ("prueba.txt", io.BytesIO(b"dummy,content\n1,2"), "text/plain")}
        res_inv = await client.post(
            "/api/v1/ingestion/upload",
            params={"tipo": "asistencia", "espacio_id": 1},
            files=files_invalid,
            headers=headers,
        )
        print(f"Status: {res_inv.status_code}, Detalle: {res_inv.json().get('detail')}")
        assert res_inv.status_code == 400

        # 2. Probar subida válida (.csv) que retorna HTTP 202
        print("\n2. Probando subida válida (.csv) que retorna HTTP 202...")
        csv_data = "Fecha,Marcajes,Primera entrada,Door entrada,Última salida,Door salida,personId\n2026-03-20,1,2026-03-20 08:30:00,Torniquete-01,2026-03-20 12:00:00,Torniquete-02,ESTUDIANTE_HTTP_1"
        files_valid = {"file": ("asistencia_http_test.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res_ok = await client.post(
            "/api/v1/ingestion/upload",
            params={"tipo": "asistencia", "espacio_id": 1, "modo_solapamiento": "merge"},
            files=files_valid,
            headers=headers,
        )
        print(f"Status: {res_ok.status_code}, Respuesta: {res_ok.json()}")
        assert res_ok.status_code == 202
        body = res_ok.json()
        job_id = body["job_id"]
        assert body["status"] == "queued"
        file_hash = body["file_hash"]

        # 3. Sondeo del job_id con GET /ingestion/{job_id}/status hasta que complete
        print(f"\n3. Sondeando estado de trabajo {job_id}...")
        for _ in range(15):
            await asyncio.sleep(1.0)
            res_st = await client.get(f"/api/v1/ingestion/{job_id}/status", headers=headers)
            st_data = res_st.json()
            print(f"Sondeo -> estado: {st_data['estado']}, registros_ok: {st_data['registros_ok']}")
            if st_data["estado"] == "completed":
                break
        assert st_data["estado"] == "completed"

        # 4. Probar rechazo de duplicado preexistente (HTTP 409)
        print("\n4. Probando rechazo de duplicado con mismo SHA-256 (HTTP 409)...")
        files_dup = {"file": ("asistencia_http_test.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")}
        res_dup = await client.post(
            "/api/v1/ingestion/upload",
            params={"tipo": "asistencia", "espacio_id": 1, "modo_solapamiento": "merge"},
            files=files_dup,
            headers=headers,
        )
        print(f"Status: {res_dup.status_code}, Detalle: {res_dup.json().get('detail')}")
        assert res_dup.status_code == 409

    print("\nTODAS LAS PRUEBAS DE ENDPOINTS PASARON EXITOSAMENTE.")


if __name__ == "__main__":
    asyncio.run(test_endpoints())
