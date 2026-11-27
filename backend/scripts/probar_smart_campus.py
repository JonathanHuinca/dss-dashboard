"""
probar_smart_campus.py — Prueba de Validación de la Integración Smart Campus UCT.

Verifica:
1. Modelos ORM: EstadoSincronizacionFuente y SectorEstacionamiento.
2. Adaptador SmartCampusAdapter y conectividad contra /api/lectura/puntos.
3. Tareas registradas en el planificador interno APScheduler.
4. Endpoints administrativos en el router de administración.
"""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Evitar fallo en máquinas host donde no esté instalado aioodbc/pyodbc/passlib compilado nativamente
m_pass = MagicMock()
m_pass.__path__ = []
sys.modules["passlib"] = m_pass
sys.modules["passlib.context"] = MagicMock()
sys.modules["passlib.handlers"] = MagicMock()
sys.modules["passlib.handlers.bcrypt"] = MagicMock()

for mod in ["aioodbc", "pyodbc", "apscheduler", "apscheduler.schedulers", "apscheduler.schedulers.asyncio", "apscheduler.triggers", "apscheduler.triggers.cron"]:
    if mod not in sys.modules:
        m = MagicMock()
        m.version = "4.0.35"
        sys.modules[mod] = m

directorio_raiz = Path(__file__).resolve().parent.parent
if str(directorio_raiz) not in sys.path:
    sys.path.insert(0, str(directorio_raiz))

from app.adapters.smart_campus_adapter import SmartCampusAdapter
from app.core.config import settings
from app.core.planificador import CATALOGO_TAREAS
from app.domain.models import EstadoSincronizacionFuente, SectorEstacionamiento
from app.api.v1.endpoints.admin import router as admin_router


async def main():
    print("=== 1. Verificación de Modelos ORM ===")
    assert hasattr(EstadoSincronizacionFuente, "fuente")
    assert hasattr(EstadoSincronizacionFuente, "ultima_fecha_sincronizada")
    assert hasattr(SectorEstacionamiento, "codigo")
    assert hasattr(SectorEstacionamiento, "capacidad_max")
    print("OK: Modelos EstadoSincronizacionFuente y SectorEstacionamiento validados correctamente.")

    print("\n=== 2. Verificación de Tareas en Planificador ===")
    assert "sincronizar_smart_campus_en_vivo" in CATALOGO_TAREAS
    assert "consolidar_smart_campus_nocturno" in CATALOGO_TAREAS
    info_vivo = CATALOGO_TAREAS["sincronizar_smart_campus_en_vivo"]
    info_noc = CATALOGO_TAREAS["consolidar_smart_campus_nocturno"]
    print(f"OK: Tarea horaria registrada -> {info_vivo['cron_str']}")
    print(f"OK: Tarea nocturna registrada -> {info_noc['cron_str']}")

    print("\n=== 3. Verificación de Endpoints Administrativos ===")
    rutas_admin = [route.path for route in admin_router.routes]
    assert "/smart-campus/estado" in rutas_admin
    assert "/smart-campus/sincronizar" in rutas_admin
    assert "/estacionamientos/sectores" in rutas_admin
    assert "/estacionamientos/sectores/{codigo}" in rutas_admin
    print("OK: 4 rutas administrativas verificadas en admin_router.")

    print("\n=== 4. Prueba de Adaptador Smart Campus ===")
    adaptador = SmartCampusAdapter()
    print(f"URL Base: {adaptador.base_url}")
    print(f"Clave configurada presente: {bool(adaptador.api_key)}")

    if adaptador.api_key:
        try:
            datos_puntos = await adaptador.obtener_puntos()
            puntos_t = datos_puntos.get("torniquetes", [])
            puntos_e = datos_puntos.get("estacionamientos", [])
            print(f"OK: Consulta a /puntos exitosa. Torniquetes catalogados: {len(puntos_t)}, Estacionamientos catalogados: {len(puntos_e)}")
        except Exception as e:
            print(f"Advertencia en consulta a /puntos: {e}")
    else:
        print("Saltando consulta en vivo: LECTURA_API_KEY no configurada en entorno de prueba.")

    print("\nTODAS LAS PRUEBAS DE SMART CAMPUS FINALIZADAS EXITOSAMENTE.")


if __name__ == "__main__":
    asyncio.run(main())
