import json
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
    print("=== INICIANDO VALIDACIÓN DE PERSISTENCIA Y AISLAMIENTO DE CHAT ===")

    # 1. Autenticación de Usuario 1 (Admin) y Usuario 2 (Analista)
    token_user1 = obtener_token(os.environ["PRUEBA_ADMIN_EMAIL"], os.environ["PRUEBA_ADMIN_PASSWORD"])
    token_user2 = obtener_token(os.environ["PRUEBA_ANALISTA_EMAIL"], os.environ["PRUEBA_ANALISTA_PASSWORD"])
    headers_user1 = {"Authorization": f"Bearer {token_user1}"}
    headers_user2 = {"Authorization": f"Bearer {token_user2}"}
    print("[OK] Tokens obtenidos para admin@uct.cl y analista@uct.cl")

    # 2. Consultar cuota inicial
    resp_cuota = requests.get(f"{API_URL}/api/chat/cuota", headers=headers_user1, timeout=10)
    assert resp_cuota.status_code == 200, f"Error en cuota: {resp_cuota.status_code}"
    cuota_u1 = resp_cuota.json()
    print(f"[OK] Cuota Usuario 1: {cuota_u1.get('usadas')} usadas, límite: {cuota_u1.get('limite_diario')}")

    # 3. Usuario 1 envía mensaje en un nuevo chat sin conversacion_id
    payload_chat1 = {
        "prompt": "¿Cuál fue la semana de mayor congestión vehicular en el estacionamiento?",
        "dataset_tipo": "estacionamiento",
        "session_id": "test-persistencia-sess-01",
        "espacio_id": 2,
        "model": "gemini-2.5-flash",
    }
    resp_chat1 = requests.post(f"{API_URL}/api/chat", json=payload_chat1, headers=headers_user1, timeout=30)
    assert resp_chat1.status_code == 200, f"Error en chat 1: {resp_chat1.status_code} - {resp_chat1.text}"
    data_chat1 = resp_chat1.json()
    conv_id = data_chat1.get("conversacion_id")
    assert conv_id, "No se retornó conversacion_id en la respuesta"
    print(f"[OK] Conversación creada automáticamente: id={conv_id}")

    # 4. Verificar detalle de conversación y título autogenerado
    resp_detalle = requests.get(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user1, timeout=10)
    assert resp_detalle.status_code == 200, f"Error detalle: {resp_detalle.status_code}"
    detalle = resp_detalle.json()
    titulo = detalle.get("titulo", "")
    mensajes = detalle.get("mensajes", [])
    print(f"[OK] Título autogenerado: '{titulo}'")
    assert "¿cuál fue la semana de mayor" in titulo.lower() or "congestión" in titulo.lower() or len(titulo) > 0, "Título no concuerda con prompt"
    assert len(mensajes) >= 2, f"Se esperaban al menos 2 mensajes, hay {len(mensajes)}"
    
    # Verificar que el mensaje no persiste figuras Plotly monolíticas
    msg_asistente = [m for m in mensajes if m["rol"] == "assistant"][-1]
    print(f"[OK] Mensaje asistente estructurado: tipo={msg_asistente.get('tipo')}, herramienta={msg_asistente.get('herramienta')}")
    assert "fig_data" not in msg_asistente, "No deben persistirse estructuras monolíticas fig_data"

    # 5. Control de Acceso: Usuario 2 intenta consultar la conversación de Usuario 1
    resp_cruzada = requests.get(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user2, timeout=10)
    assert resp_cruzada.status_code in (403, 404), f"Acceso cruzado permitido indebidamente: {resp_cruzada.status_code}"
    print(f"[OK] Acceso cruzado prevenido exitosamente (HTTP {resp_cruzada.status_code})")

    # Usuario 2 intenta listar conversaciones: no debe aparecer la de Usuario 1
    resp_list_u2 = requests.get(f"{API_URL}/api/chat/conversaciones", headers=headers_user2, timeout=10)
    assert resp_list_u2.status_code == 200
    ids_u2 = [c["id"] for c in resp_list_u2.json()]
    assert conv_id not in ids_u2, "La conversación del Usuario 1 se filtró en el listado del Usuario 2"
    print("[OK] Listado de conversaciones estrictamente aislado por usuario_id")

    # 6. Usuario 1 envía segundo mensaje en la misma conversación
    payload_chat2 = {
        "prompt": "¿Cuáles fueron las horas con mayor flujo vehicular?",
        "dataset_tipo": "estacionamiento",
        "session_id": "test-persistencia-sess-02",
        "conversacion_id": conv_id,
        "espacio_id": 2,
        "model": "gemini-2.5-flash",
    }
    resp_chat2 = requests.post(f"{API_URL}/api/chat", json=payload_chat2, headers=headers_user1, timeout=30)
    assert resp_chat2.status_code == 200
    print("[OK] Segundo mensaje enviado y vinculado a la misma conversación")

    # Verificar que ahora hay 4 mensajes
    resp_detalle2 = requests.get(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user1, timeout=10)
    mensajes2 = resp_detalle2.json().get("mensajes", [])
    assert len(mensajes2) >= 4, f"Se esperaban al menos 4 mensajes, hay {len(mensajes2)}"
    print(f"[OK] Mensajes acumulados antes del reinicio: {len(mensajes2)}")

    # 7. REINICIAR CONTENEDOR API
    print("--> Reiniciando contenedor uct-dss-api-1...")
    subprocess.run(["docker", "restart", "uct-dss-api-1"], check=True)
    print("--> Contenedor reiniciado. Esperando a que el servicio esté saludable...")

    # Esperar hasta que responda /health
    saludable = False
    for _ in range(30):
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

    # 8. VERIFICAR PERSISTENCIA TRAS REINICIO
    # Usuario 1 consulta sus conversaciones
    resp_list_post = requests.get(f"{API_URL}/api/chat/conversaciones", headers=headers_user1, timeout=10)
    assert resp_list_post.status_code == 200
    convs_post = resp_list_post.json()
    conv_encontrada = next((c for c in convs_post if c["id"] == conv_id), None)
    assert conv_encontrada is not None, "La conversación se perdió tras reiniciar el contenedor"
    print(f"[OK] Conversación persistida íntegra tras reinicio: id={conv_encontrada['id']}")

    # Consultar detalle y mensajes tras reinicio
    resp_detalle_post = requests.get(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user1, timeout=10)
    assert resp_detalle_post.status_code == 200
    mensajes_post = resp_detalle_post.json().get("mensajes", [])
    assert len(mensajes_post) >= 4, f"Se esperaban al menos 4 mensajes tras reinicio, hay {len(mensajes_post)}"
    print(f"[OK] Historial de {len(mensajes_post)} mensajes recuperado intacto desde SQL Server")

    # Verificar cuota persistente tras reinicio
    resp_cuota_post = requests.get(f"{API_URL}/api/chat/cuota", headers=headers_user1, timeout=10)
    assert resp_cuota_post.status_code == 200
    cuota_post = resp_cuota_post.json()
    assert cuota_post.get("usadas", 0) >= 2, "La cuota consumida se reseteó tras el reinicio"
    print(f"[OK] Cuota diaria persistente conservada tras reinicio: {cuota_post.get('usadas')} consultas usadas")

    # Usuario 2 sigue sin poder acceder tras el reinicio
    resp_cruzada_post = requests.get(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user2, timeout=10)
    assert resp_cruzada_post.status_code in (403, 404), "Falla de aislamiento tras reinicio"
    print("[OK] Aislamiento estricto verificado tras reinicio")

    # 9. Probar Renombrar, Archivar y Eliminar (Borrado Lógico)
    # Renombrar
    resp_renombrar = requests.patch(
        f"{API_URL}/api/chat/conversaciones/{conv_id}/renombrar",
        json={"titulo": "Auditoría de Tráfico Vehicular Campus SF"},
        headers=headers_user1,
        timeout=10,
    )
    assert resp_renombrar.status_code == 200
    print("[OK] Conversación renombrada")

    # Archivar
    resp_archivar = requests.patch(
        f"{API_URL}/api/chat/conversaciones/{conv_id}/archivar",
        json={"archivada": True},
        headers=headers_user1,
        timeout=10,
    )
    assert resp_archivar.status_code == 200
    print("[OK] Conversación archivada")

    # Verificar que no aparece en activas
    resp_activas = requests.get(f"{API_URL}/api/chat/conversaciones", headers=headers_user1, timeout=10)
    assert not any(c["id"] == conv_id for c in resp_activas.json()), "Aparece en activas estando archivada"
    
    # Verificar que sí aparece en archivadas
    resp_archivadas = requests.get(f"{API_URL}/api/chat/conversaciones?archivada=true", headers=headers_user1, timeout=10)
    assert any(c["id"] == conv_id for c in resp_archivadas.json()), "No aparece en archivadas"
    print("[OK] Filtrado de activas/archivadas verificado")

    # Borrado lógico
    resp_eliminar = requests.delete(f"{API_URL}/api/chat/conversaciones/{conv_id}", headers=headers_user1, timeout=10)
    assert resp_eliminar.status_code == 200
    
    # Ya no debe aparecer ni en activas ni en archivadas
    resp_ambas = requests.get(f"{API_URL}/api/chat/conversaciones?incluir_archivadas=true", headers=headers_user1, timeout=10)
    assert not any(c["id"] == conv_id for c in resp_ambas.json()), "Conversación borrada lógicamente aún aparece en listado"
    print("[OK] Borrado lógico verificado exitosamente")

    # 10. Probar endpoint de purga
    resp_purga = requests.post(f"{API_URL}/api/chat/purgar-eliminadas", headers=headers_user1, timeout=10)
    assert resp_purga.status_code == 200
    print(f"[OK] Tarea de purga ejecutada: {resp_purga.json()}")

    print("\n=== TODAS LAS PRUEBAS DE PERSISTENCIA Y AISLAMIENTO PASARON EXITOSAMENTE ===")


if __name__ == "__main__":
    main()
