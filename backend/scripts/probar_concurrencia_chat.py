import asyncio
import os
import time
import httpx

API_BASE = "http://127.0.0.1:8000"

async def test_concurrency():
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
        # 1. Autenticación
        print("1. Autenticando usuario admin...")
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": os.environ["PRUEBA_ADMIN_EMAIL"], "password": os.environ["PRUEBA_ADMIN_PASSWORD"]},
        )
        if login_res.status_code != 200:
            print(f"Error login: {login_res.status_code} - {login_res.text}")
            return False

        token = login_res.json().get("access_token")
        headers = {"Authorization": f"Bearer {token}"}
        print("Token JWT obtenido exitosamente.")

        # 2. Definir consultas de chat simultáneas
        payloads = [
            {"prompt": "Cuál fue el aforo del 10 al 15 de abril de 2026?", "dataset_tipo": "biblioteca", "espacio_id": 1, "session_id": "sess-1"},
            {"prompt": "Cuál fue la ocupación vehicular entre las 8 y las 11 hrs?", "dataset_tipo": "estacionamiento", "espacio_id": 2, "session_id": "sess-2"},
            {"prompt": "Muestra el mapa de calor de concurrencia", "dataset_tipo": "biblioteca", "espacio_id": 1, "session_id": "sess-3"},
            {"prompt": "Cuáles son los picos de afluencia de estudiantes?", "dataset_tipo": "biblioteca", "espacio_id": 1, "session_id": "sess-4"},
            {"prompt": "Cuáles son los accesos por torniquetes en biblioteca?", "dataset_tipo": "biblioteca", "espacio_id": 1, "session_id": "sess-5"},
        ]

        # 3. Función para enviar consulta de chat
        async def enviar_chat(idx, payload):
            t0 = time.perf_counter()
            try:
                res = await client.post("/api/chat", json=payload, headers=headers)
                dt = (time.perf_counter() - t0) * 1000
                print(f"Chat {idx} completado: status {res.status_code} en {dt:.1f}ms")
                return res.status_code
            except Exception as e:
                dt = (time.perf_counter() - t0) * 1000
                print(f"Chat {idx} error: {e} en {dt:.1f}ms")
                return 500

        # 4. Función para monitorear GET /health continuamente
        health_latencies = []
        stop_monitoring = asyncio.Event()

        async def monitor_health():
            # Pequeño retardo de 50ms para asegurar que las peticiones de chat ya ingresaron al servidor
            await asyncio.sleep(0.05)
            while not stop_monitoring.is_set():
                t0 = time.perf_counter()
                try:
                    res = await client.get("/health")
                    latency_ms = (time.perf_counter() - t0) * 1000
                    health_latencies.append((res.status_code, latency_ms))
                except Exception as e:
                    health_latencies.append((500, 9999.0))
                await asyncio.sleep(0.03)

        print("2. Disparando 5 consultas simultáneas de chat y monitoreando GET /health...")
        monitor_task = asyncio.create_task(monitor_health())
        chat_tasks = [enviar_chat(i, p) for i, p in enumerate(payloads)]

        await asyncio.gather(*chat_tasks)
        stop_monitoring.set()
        await monitor_task

        # 5. Evaluar criterio de aceptación
        print("\n3. Resultados de monitoreo de GET /health durante consultas simultáneas:")
        print(f"Total mediciones de /health realizadas: {len(health_latencies)}")
        if not health_latencies:
            print("No se registraron mediciones de /health.")
            return False

        latencias = [lat for _, lat in health_latencies]
        max_lat = max(latencias)
        min_lat = min(latencias)
        avg_lat = sum(latencias) / len(latencias)

        print(f"Latencia mínima /health: {min_lat:.2f} ms")
        print(f"Latencia promedio /health: {avg_lat:.2f} ms")
        print(f"Latencia máxima /health: {max_lat:.2f} ms")

        cumple = all(lat < 200.0 and status == 200 for status, lat in health_latencies)
        if cumple:
            print("\nCRITERIO DE ACEPTACIÓN CUMPLIDO: Todas las respuestas de GET /health respondieron en menos de 200 ms.")
            return True
        else:
            print(f"\nCRITERIO NO CUMPLIDO: Hubo solicitudes de /health superiores a 200 ms (máx: {max_lat:.2f} ms).")
            return False

if __name__ == "__main__":
    exito = asyncio.run(test_concurrency())
    exit(0 if exito else 1)
