"""
probar_planificador_tareas.py — Validación de planificador interno APScheduler,
control de reentrancia atómica en base de datos y persistencia tras reinicio.
"""

import concurrent.futures
import os
import subprocess
import time
import requests

API_URL = "http://localhost:8000"


def obtener_token(email: str, password: str) -> str:
    url = f"{API_URL}/api/v1/auth/login"
    resp = requests.post(url, json={"email": email, "password": password}, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"Fallo en login de {email}: HTTP {resp.status_code} - {resp.text}")
    return resp.json()["access_token"]


def main():
    print("=== INICIANDO VALIDACIÓN DEL PLANIFICADOR INTERNO Y CONTROL DE REENTRANCIA ===")

    # 1. Obtención de tokens
    token_admin = obtener_token(os.environ["PRUEBA_ADMIN_EMAIL"], os.environ["PRUEBA_ADMIN_PASSWORD"])
    token_analista = obtener_token(os.environ["PRUEBA_ANALISTA_EMAIL"], os.environ["PRUEBA_ANALISTA_PASSWORD"])
    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    headers_analista = {"Authorization": f"Bearer {token_analista}"}
    print("[OK] Tokens obtenidos para Admin_Sistema y Analista")

    # 2. Control de Acceso RBAC: Analista no debe tener acceso a /admin/tareas
    r_no_auth_get = requests.get(f"{API_URL}/api/v1/admin/tareas", headers=headers_analista, timeout=10)
    assert r_no_auth_get.status_code == 403, f"Se esperaba 403 para analista en GET, se obtuvo {r_no_auth_get.status_code}"
    r_no_auth_post = requests.post(f"{API_URL}/api/v1/admin/tareas/tarea_prueba/ejecutar", headers=headers_analista, timeout=10)
    assert r_no_auth_post.status_code == 403, f"Se esperaba 403 para analista en POST, se obtuvo {r_no_auth_post.status_code}"
    print("[OK] Control RBAC validado: solo Admin_Sistema puede consultar o ejecutar tareas")

    # 3. Consulta de catálogo y estado inicial por Admin_Sistema
    r_cat = requests.get(f"{API_URL}/api/v1/admin/tareas", headers=headers_admin, timeout=10)
    assert r_cat.status_code == 200, f"Error obteniendo catálogo: {r_cat.status_code}"
    datos_cat = r_cat.json()
    assert datos_cat.get("planificador_activo") is True, "El planificador interno debe reportarse activo"
    catalogo = datos_cat.get("catalogo", [])
    nombres_catalogo = [t["nombre"] for t in catalogo]
    print(f"[OK] Catálogo de tareas disponible ({len(catalogo)} tareas): {nombres_catalogo}")
    assert "reentrenar_modelos_ml" in nombres_catalogo, "Falta reentrenar_modelos_ml en catálogo"
    assert "purgar_conversaciones_chat" in nombres_catalogo, "Falta purgar_conversaciones_chat en catálogo"
    assert "tarea_prueba" in nombres_catalogo, "Falta tarea_prueba en catálogo"

    # 4. PRUEBA CRÍTICA DE REENTRANCIA: Dos solicitudes simultáneas de ejecución
    print("\n--> Disparando 2 solicitudes simultáneas a /admin/tareas/tarea_prueba/ejecutar...")
    
    def _disparar_ejecucion():
        return requests.post(
            f"{API_URL}/api/v1/admin/tareas/tarea_prueba/ejecutar",
            headers=headers_admin,
            timeout=10,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(_disparar_ejecucion)
        f2 = executor.submit(_disparar_ejecucion)
        r1 = f1.result()
        r2 = f2.result()

    codigos = sorted([r1.status_code, r2.status_code])
    print(f"Respuestas recibidas: {r1.status_code} y {r2.status_code}")
    assert codigos == [200, 409], f"Se esperaba exactamente un 200 y un 409 por reentrancia, se obtuvo: {codigos}"
    print("[OK] Control de reentrancia atómico verificado: 1 tarea activa y 1 rechazada con HTTP 409 Conflict")

    # Obtener el ID de la tarea exitosamente iniciada
    resp_exitosa = r1.json() if r1.status_code == 200 else r2.json()
    tarea_id = resp_exitosa["id"]
    print(f"[OK] Tarea en ejecución iniciada con id={tarea_id}, estado inicial='{resp_exitosa.get('estado')}'")

    # 5. Esperar a que la tarea complete su ejecución (tarea_prueba toma ~2s)
    completada = False
    for _ in range(15):
        time.sleep(1)
        r_check = requests.get(f"{API_URL}/api/v1/admin/tareas", headers=headers_admin, timeout=5)
        if r_check.status_code == 200:
            historial = r_check.json().get("ultimas_ejecuciones", [])
            ej = next((e for e in historial if e["id"] == tarea_id), None)
            if ej and ej["estado"] in ("exitoso", "fallido"):
                completada = True
                assert ej["estado"] == "exitoso", f"La tarea terminó en estado no exitoso: {ej['estado']}, error={ej.get('error')}"
                assert ej["fin_en"] is not None, "fin_en debe estar poblado al terminar"
                assert ej["duracion_segundos"] is not None and ej["duracion_segundos"] >= 0, "duracion_segundos debe calcularse"
                assert ej["memoria_pico_mb"] is not None, "memoria_pico_mb debe registrarse"
                print(f"[OK] Tarea finalizada exitosamente: duracion={ej['duracion_segundos']}s, memoria={ej['memoria_pico_mb']} MB")
                break

    assert completada, "La tarea no finalizó en el tiempo esperado"

    # 6. REINICIAR CONTENEDOR API
    print("\n--> Reiniciando contenedor uct-dss-api-1 para validar persistencia...")
    subprocess.run(["docker", "restart", "uct-dss-api-1"], check=True)
    print("--> Esperando restablecimiento del servicio...")

    saludable = False
    for _ in range(35):
        time.sleep(1)
        try:
            r = requests.get(f"{API_URL}/health", timeout=2)
            if r.status_code == 200:
                saludable = True
                break
        except Exception:
            pass

    assert saludable, "La API no volvió a estar saludable tras el reinicio"
    print("[OK] Contenedor API saludable tras reinicio")

    # 7. VERIFICAR PERSISTENCIA DEL ESTADO TRAS REINICIO
    r_post_restart = requests.get(f"{API_URL}/api/v1/admin/tareas", headers=headers_admin, timeout=10)
    assert r_post_restart.status_code == 200
    historial_post = r_post_restart.json().get("ultimas_ejecuciones", [])
    ej_persistida = next((e for e in historial_post if e["id"] == tarea_id), None)
    assert ej_persistida is not None, "El registro de ejecución de la tarea se perdió tras el reinicio"
    assert ej_persistida["estado"] == "exitoso", f"El estado persistido es incorrecto: {ej_persistida['estado']}"
    assert ej_persistida["memoria_pico_mb"] is not None, "La métrica de memoria persistida es nula"
    print(f"[OK] Persistencia verificada: Registro {tarea_id} permanece íntegro con estado='exitoso' tras reinicio")

    # 8. Comprobar que el planificador volvió a arrancar y limpió huérfanas
    assert r_post_restart.json().get("planificador_activo") is True, "El planificador debe reanudarse activo tras reinicio"
    print("[OK] Planificador activo y operativo post-reinicio")

    print("\n=== TODAS LAS VALIDACIONES DEL PLANIFICADOR Y REENTRANCIA PASARON CON ÉXITO ===")


if __name__ == "__main__":
    main()
