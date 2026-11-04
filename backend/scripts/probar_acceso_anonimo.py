"""
probar_acceso_anonimo.py — Verificación de seguridad de endpoints frente a peticiones anónimas.

Recorre todas las rutas registradas en la aplicación FastAPI, realiza peticiones GET sin cabecera
de autorización y comprueba que ningún endpoint fuera de la lista blanca pública retorne código 200.
"""

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import List, Set, Tuple

# Asegurar que el directorio raíz de la aplicación se encuentre en sys.path
directorio_raiz = Path(__file__).resolve().parent.parent
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

import httpx
from app.main import app

# Lista blanca institucional de rutas públicas que permiten acceso anónimo
RUTAS_PUBLICAS_PERMITIDAS: Set[str] = {
    "/health",
    "/api/v1/auth/verify-token",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
}


def extraer_rutas_get() -> List[str]:
    """
    Extrae recursivamente todas las rutas con método GET registradas en la aplicación FastAPI.
    """
    rutas_encontradas: Set[str] = set()

    def inspeccionar_rutas(lista_rutas):
        for elemento in lista_rutas:
            if hasattr(elemento, "effective_route_contexts"):
                for contexto in elemento.effective_route_contexts():
                    if contexto.methods and "GET" in contexto.methods:
                        rutas_encontradas.add(contexto.path)
            elif hasattr(elemento, "routes"):
                inspeccionar_rutas(elemento.routes)
            elif hasattr(elemento, "path") and getattr(elemento, "methods", None):
                if "GET" in elemento.methods:
                    rutas_encontradas.add(elemento.path)

    inspeccionar_rutas(app.routes)
    return sorted(list(rutas_encontradas))


def normalizar_ruta_con_parametros(ruta_patron: str) -> str:
    """
    Reemplaza parámetros de ruta {param} por identificadores de prueba válidos.
    """
    ruta = ruta_patron
    ruta = re.sub(r"\{job_id\}", "00000000-0000-0000-0000-000000000000", ruta)
    ruta = re.sub(r"\{espacio_id\}", "1", ruta)
    ruta = re.sub(r"\{user_id\}", "1", ruta)
    ruta = re.sub(r"\{[a-zA-Z0-9_]+\}", "1", ruta)
    return ruta


async def ejecutar_verificacion() -> int:
    """
    Ejecuta peticiones GET a cada endpoint sin token de autenticación.
    Retorna 0 si no se detectan accesos anónimos indebidos, o 1 si existen fallos de seguridad.
    """
    rutas_get = extraer_rutas_get()
    fallos_seguridad: List[Tuple[str, int]] = []
    rutas_protegidas_exitosas = 0
    rutas_publicas_verificadas = 0

    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://testserver") as cliente:
        for patron_ruta in rutas_get:
            ruta_solicitud = normalizar_ruta_con_parametros(patron_ruta)
            
            try:
                respuesta = await cliente.get(ruta_solicitud)
                codigo_estado = respuesta.status_code
            except Exception as error_peticion:
                print(f"Error al solicitar {ruta_solicitud}: {error_peticion}")
                codigo_estado = 500

            es_publica = patron_ruta in RUTAS_PUBLICAS_PERMITIDAS

            if es_publica:
                rutas_publicas_verificadas += 1
            else:
                if 200 <= codigo_estado < 300:
                    fallos_seguridad.append((patron_ruta, codigo_estado))
                    print(f"[VULNERABILIDAD] {patron_ruta} -> {codigo_estado} (debio requerir token)")
                else:
                    rutas_protegidas_exitosas += 1

    print("\n--- RESUMEN DE AUDITORIA DE ACCESO ANONIMO ---")
    print(f"Total rutas GET analizadas: {len(rutas_get)}")
    print(f"Rutas publicas autorizadas: {rutas_publicas_verificadas}")
    print(f"Rutas protegidas verificadas (401/403/rechazo): {rutas_protegidas_exitosas}")
    print(f"Endpoints publicos no autorizados: {len(fallos_seguridad)}")

    if fallos_seguridad:
        print("\nFALLO: Se encontraron endpoints publicos no autorizados que responden 2xx sin token:")
        for ruta, estado in fallos_seguridad:
            print(f"  - {ruta} (HTTP {estado})")
        return 1

    print("\nEXITO: 0 endpoints publicos no autorizados. Todas las rutas protegidas requieren autenticacion.")
    return 0


if __name__ == "__main__":
    codigo_salida = asyncio.run(ejecutar_verificacion())
    sys.exit(codigo_salida)
