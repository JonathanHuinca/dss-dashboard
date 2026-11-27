"""
probar_calendario_anual.py — Suite de pruebas de validación para el Prompt 8:
Sincronización anual del calendario, analizador sintáctico de fechas, reintentos y control RBAC.
"""
import asyncio
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import httpx
from sqlalchemy import select, delete
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.planificador import CATALOGO_TAREAS, ZONA_HORARIA_CHILE
from app.core.security import create_access_token
from app.domain.auth_models import Rol, Usuario, UsuarioRol
from app.domain.models import EstadoCalendarioAnual, CalendarioAcademico
from app.services.calendar_scraper import analizar_fechas_calendario
from app.services.servicio_calendario_anual import (
    sincronizar_calendario_anual,
    obtener_estado_calendario_anual,
    enviar_alerta_correo_administrador,
)
from app.main import app


async def probar_calendario_anual():
    print("\n========================================================")
    print("      VERIFICACIÓN PROMPT 8: CALENDARIO ANUAL UCT       ")
    print("========================================================\n")

    # 1. Probar analizador sintáctico de fechas (fechas con guión vs rangos)
    print("[1/5] Verificando analizador sintáctico de fechas...")
    # A. Fechas individuales con guiones (dd-mm-yyyy)
    f_individual_1 = analizar_fechas_calendario("25-12-2026")
    assert len(f_individual_1) == 1 and f_individual_1[0] == date(2026, 12, 25), f"Fallo fecha dd-mm-yyyy: {f_individual_1}"
    
    f_individual_2 = analizar_fechas_calendario("2026-05-01")
    assert len(f_individual_2) == 1 and f_individual_2[0] == date(2026, 5, 1), f"Fallo fecha yyyy-mm-dd: {f_individual_2}"

    f_individual_3 = analizar_fechas_calendario("08/12/2026")
    assert len(f_individual_3) == 1 and f_individual_3[0] == date(2026, 12, 8), f"Fallo fecha dd/mm/yyyy: {f_individual_3}"

    # B. Rangos de fechas con guiones y separadores
    f_rango_1 = analizar_fechas_calendario("01-03-2026 - 05-03-2026")
    assert len(f_rango_1) == 5, f"Esperado 5 días en rango, obtenido {len(f_rango_1)}"
    assert f_rango_1[0] == date(2026, 3, 1) and f_rango_1[-1] == date(2026, 3, 5)

    f_rango_2 = analizar_fechas_calendario("10 al 14-04-2026")
    assert len(f_rango_2) == 5, f"Esperado 5 días en rango 'al', obtenido {len(f_rango_2)}"
    assert f_rango_2[0] == date(2026, 4, 10) and f_rango_2[-1] == date(2026, 4, 14)

    f_rango_3 = analizar_fechas_calendario("18-09-2026 a 20-09-2026")
    assert len(f_rango_3) == 3, f"Esperado 3 días en rango 'a', obtenido {len(f_rango_3)}"

    print("      -> APROBADO: Analizador sintáctico diferencia correctamente fechas individuales y rangos.")

    # 2. Verificar agenda de la tarea en planificador
    print("\n[2/5] Verificando agenda anual en el planificador (1 de enero 03:00)...")
    assert "verificar_calendario_anual" in CATALOGO_TAREAS, "verificar_calendario_anual no existe en CATALOGO_TAREAS"
    tarea_cal = CATALOGO_TAREAS["verificar_calendario_anual"]
    print(f"      - Cron registrado: {tarea_cal['cron_str']}")
    print(f"      - Frecuencia: {tarea_cal['frecuencia']}")
    print(f"      - Mes/Día/Hora catchup: Día {tarea_cal.get('catchup_dia')}/{tarea_cal.get('catchup_mes')} a las {tarea_cal.get('catchup_hora'):02d}:{tarea_cal.get('catchup_minuto'):02d}")
    assert tarea_cal["frecuencia"] == "anual"
    assert tarea_cal["catchup_mes"] == 1 and tarea_cal["catchup_dia"] == 1 and tarea_cal["catchup_hora"] == 3
    print("      -> APROBADO: Tarea 'verificar_calendario_anual' correctamente configurada.")

    # 3. Probar lógica de sincronización: 'pendiente' vs 'completo', reintentos a 7 días y alerta tras 3 intentos
    print("\n[3/5] Verificando lógica de negocio y reintentos semanales en servicio...")
    anio_test = 2099  # Año de prueba aislado
    async with AsyncSessionLocal() as session:
        # Limpieza previa
        await session.execute(delete(EstadoCalendarioAnual).where(EstadoCalendarioAnual.anio_objetivo == anio_test))
        await session.commit()

        # Simular scraping que no encuentra eventos suficientes para el año objetivo
        with patch("app.services.servicio_calendario_anual.scrape_and_sync_uct_calendar", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.return_value = {"status": "success", "total_days": 5}
            
            # Intento 1: Menos de MINIMO_EVENTOS_CALENDARIO -> 'pendiente', proximo reintento en 7 días
            res1 = await sincronizar_calendario_anual(session, anio_objetivo=anio_test, forzar=True)
            print(f"      - Intento 1: estado={res1['estado']}, intentos={res1['intentos']}")
            assert res1["estado"] == "pendiente"
            assert res1["intentos"] == 1
            st1 = await obtener_estado_calendario_anual(session, anio_test)
            assert st1.proximo_intento_en is not None
            delta_1 = (st1.proximo_intento_en - st1.ultimo_intento_en).days
            assert delta_1 == 7, f"Esperado reintento en 7 días exactos, obtenido {delta_1}"

            # Intento 2:
            res2 = await sincronizar_calendario_anual(session, anio_objetivo=anio_test, forzar=True)
            print(f"      - Intento 2: estado={res2['estado']}, intentos={res2['intentos']}")
            assert res2["intentos"] == 2 and res2["estado"] == "pendiente"

            # Intento 3: debe disparar alerta por correo tras 3 intentos consecutivos
            with patch("app.services.servicio_calendario_anual.enviar_alerta_correo_administrador", new_callable=AsyncMock) as mock_alerta:
                mock_alerta.return_value = True
                res3 = await sincronizar_calendario_anual(session, anio_objetivo=anio_test, forzar=True)
                print(f"      - Intento 3: estado={res3['estado']}, intentos={res3['intentos']}")
                assert res3["intentos"] == 3
                # Esperar microtarea para asegurar llamada
                await asyncio.sleep(0.05)
                assert mock_alerta.called, "Debió enviarse alerta al administrador tras 3 intentos fallidos"
                print("        Alerta por correo al administrador tras 3 intentos fallidos: DISPARADA")

        # Ahora simular que la web publica el calendario y se encuentran suficientes eventos
        for i in range(1, settings.MINIMO_EVENTOS_CALENDARIO + 5):
            f_mock = date(anio_test, 3, (i % 28) + 1)
            session.add(CalendarioAcademico(
                fecha=f_mock,
                is_class_milestone=True,
                descripcion=f"Hito de prueba {i}",
                fuente="test"
            ))
        await session.commit()

        # Intento con eventos suficientes: debe marcar 'completo' y detener reintentos
        with patch("app.services.servicio_calendario_anual.scrape_and_sync_uct_calendar", new_callable=AsyncMock) as mock_scrape_ok:
            mock_scrape_ok.return_value = {"status": "success", "total_days": 25}
            res_ok = await sincronizar_calendario_anual(session, anio_objetivo=anio_test, forzar=True)
            print(f"      - Con eventos suficientes: estado={res_ok['estado']}, eventos={res_ok['eventos_encontrados']}")
            assert res_ok["estado"] == "completo"
            st_ok = await obtener_estado_calendario_anual(session, anio_test)
            assert st_ok.proximo_intento_en is None, "Debe detener los reintentos al quedar 'completo'"
            assert st_ok.ultimo_error is None

        # Limpieza de datos de prueba
        await session.execute(delete(CalendarioAcademico).where(CalendarioAcademico.fecha >= date(anio_test, 1, 1)))
        await session.execute(delete(EstadoCalendarioAnual).where(EstadoCalendarioAnual.anio_objetivo == anio_test))
        await session.commit()

    print("      -> APROBADO: Lógica de 'pendiente', 'completo', reintentos a 7 días y alertas validada.")

    # 4. Probar Endpoints solo Admin_Sistema
    print("\n[4/5] Verificando endpoints y seguridad RBAC en /api/v1/admin/calendario...")
    async with AsyncSessionLocal() as session:
        stmt_admin = select(Usuario).join(Usuario.usuario_roles).join(UsuarioRol.rol).where(Rol.nombre.in_(["Admin_Sistema", "SuperAdmin"]))
        admin_u = (await session.execute(stmt_admin)).scalars().first()

        stmt_no_admin = select(Usuario).join(Usuario.usuario_roles).join(UsuarioRol.rol).where(Rol.nombre.notin_(["Admin_Sistema", "SuperAdmin"]))
        no_admin_u = (await session.execute(stmt_no_admin)).scalars().first()

        token_admin = create_access_token(user_id=admin_u.id, rol="Admin_Sistema", roles=["Admin_Sistema"])
        token_no_admin = create_access_token(user_id=no_admin_u.id, rol="Analista_Consulta", roles=["Analista_Consulta"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # A. GET /api/v1/admin/calendario/estado
        r_anon = await client.get("/api/v1/admin/calendario/estado")
        assert r_anon.status_code == 401, f"Esperado 401, recibido {r_anon.status_code}"

        r_no_admin = await client.get("/api/v1/admin/calendario/estado", headers={"Authorization": f"Bearer {token_no_admin}"})
        assert r_no_admin.status_code == 403, f"Esperado 403, recibido {r_no_admin.status_code}"

        r_admin = await client.get("/api/v1/admin/calendario/estado", headers={"Authorization": f"Bearer {token_admin}"})
        assert r_admin.status_code == 200, f"Esperado 200, recibido {r_admin.status_code}"
        print(f"      - GET /calendario/estado: HTTP {r_admin.status_code} | Registros: {len(r_admin.json())}")

        # B. POST /api/v1/admin/calendario/sincronizar
        r_post_no_admin = await client.post("/api/v1/admin/calendario/sincronizar", headers={"Authorization": f"Bearer {token_no_admin}"})
        assert r_post_no_admin.status_code == 403, f"Esperado 403, recibido {r_post_no_admin.status_code}"

        r_post_admin = await client.post("/api/v1/admin/calendario/sincronizar?anio=2026", headers={"Authorization": f"Bearer {token_admin}"})
        assert r_post_admin.status_code == 200, f"Esperado 200, recibido {r_post_admin.status_code}"
        print(f"      - POST /calendario/sincronizar: HTTP {r_post_admin.status_code} | Respuesta: {r_post_admin.json().get('status')}")

    print("      -> APROBADO: Endpoints administrativos y RBAC conformes a especificación.")

    # 5. Invalidación de caché tras sincronización
    print("\n[5/5] Verificando invalidación de cachés de aforo y marcado de reentrenamiento...")
    from app.ml.gestor_modelos import _cache_modelos_memoria
    _cache_modelos_memoria["test_key"] = (12345.0, "dummy_model")
    from app.services.servicio_calendario_anual import invalidar_caches_aforo_y_marcar_reentrenamiento
    invalidar_caches_aforo_y_marcar_reentrenamiento()
    assert len(_cache_modelos_memoria) == 0, "La caché de modelos debió vaciarse"
    print("      -> APROBADO: Invalidación de caché completada.")

    print("\n========================================================")
    print("      TODAS LAS PRUEBAS COMPLETADAS EXITOSAMENTE        ")
    print("========================================================\n")


if __name__ == "__main__":
    asyncio.run(probar_calendario_anual())
