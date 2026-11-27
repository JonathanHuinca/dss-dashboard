"""
auditoria_integridad_matematica.py — Auditoría de integridad numérica sobre dataset fixture controlado.
Contrasta los valores esperados analíticamente contra las salidas reales de AttendanceService y VehicleService.
"""
import asyncio
import os
import sys
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.attendance_service import (
    AttendanceService,
    _calcular_curva_presencia_por_hora,
)
from app.services.vehicle_service import (
    VehicleService,
    _calcular_curva_presencia_vehicular_por_hora,
)


def _crear_sesion_mock_filas(filas_primera: list[SimpleNamespace]) -> AsyncMock:
    db = AsyncMock()
    resultados = []
    for fila in filas_primera:
        res = MagicMock()
        res.first.return_value = fila
        res.one.return_value = fila
        resultados.append(res)
    db.execute = AsyncMock(side_effect=resultados)
    return db


async def _auditar_servicios() -> list[tuple[str, str, float, float]]:
    ahora_ref = datetime(2026, 10, 14, 18, 0, 0)
    fecha_ev = date(2026, 10, 14)

    # 1. Fixture controlado para barrido cronológico de presencia peatonal (AttendanceService)
    sesiones_bib = [
        (fecha_ev, 1, datetime(2026, 10, 14, 9, 30, 0), datetime(2026, 10, 14, 10, 30, 0)),
        (fecha_ev, 1, datetime(2026, 10, 14, 10, 10, 0), datetime(2026, 10, 14, 10, 45, 0)),
        (fecha_ev, 2, datetime(2026, 10, 14, 10, 15, 0), datetime(2026, 10, 14, 11, 20, 0)),
    ]
    flujo_bib = [
        SimpleNamespace(bucket=datetime(2026, 10, 14, 9, 0, 0), fecha=fecha_ev, ingresos=1, salidas=0, ingresos_sala1=1, ingresos_sala2=0),
        SimpleNamespace(bucket=datetime(2026, 10, 14, 10, 0, 0), fecha=fecha_ev, ingresos=2, salidas=2, ingresos_sala1=1, ingresos_sala2=1),
        SimpleNamespace(bucket=datetime(2026, 10, 14, 11, 0, 0), fecha=fecha_ev, ingresos=0, salidas=1, ingresos_sala1=0, ingresos_sala2=0),
    ]
    curva_bib = _calcular_curva_presencia_por_hora(sesiones_bib, flujo_bib, ahora_ref)
    pico_bib_10 = next(p for p in curva_bib if p["bucket"].endswith("10:00:00"))
    pico_bib_11 = next(p for p in curva_bib if p["bucket"].endswith("11:00:00"))

    # 2. Fixture controlado para AttendanceService.get_kpis
    fila_bib = SimpleNamespace(
        total_registros=3,
        usuarios_unicos=2,
        total_registros_sala1=2,
        total_registros_sala2=1,
        usuarios_unicos_sala1=2,
        usuarios_unicos_sala2=1,
        dias_operativos=1,
        permanencia_promedio_min=60.0,
        tasa_rebote_pct=33.33,
        horas_estudiante_total=3.0,
        permanencia_mediana_min=50.0,
        hora_punta_num=10,
    )
    db_bib = _crear_sesion_mock_filas([fila_bib])
    with (
        patch.object(AttendanceService, "_build_attendance_filters", new=AsyncMock(return_value=("1=1", {}))),
        patch.object(AttendanceService, "get_realtime_presence_curve", new=AsyncMock(return_value=curva_bib)),
    ):
        kpis_bib = await AttendanceService.get_kpis(db_bib, espacio_id=1, fecha_inicio=fecha_ev, fecha_fin=fecha_ev)

    # 3. Fixture controlado para barrido cronológico vehicular (VehicleService)
    sesiones_veh = [
        (fecha_ev, 1, datetime(2026, 10, 14, 8, 10, 0), datetime(2026, 10, 14, 9, 40, 0)),
        (fecha_ev, 2, datetime(2026, 10, 14, 8, 20, 0), datetime(2026, 10, 14, 8, 50, 0)),
        (fecha_ev, 3, datetime(2026, 10, 14, 8, 30, 0), datetime(2026, 10, 14, 9, 10, 0)),
    ]
    flujo_veh = [
        SimpleNamespace(
            bucket=datetime(2026, 10, 14, 8, 0, 0),
            fecha=fecha_ev,
            entradas=3,
            salidas=1,
            entradas_csf11=1,
            salidas_csf11=0,
            entradas_csf21=1,
            salidas_csf21=1,
            entradas_chs01=1,
            salidas_chs01=0,
        ),
        SimpleNamespace(
            bucket=datetime(2026, 10, 14, 9, 0, 0),
            fecha=fecha_ev,
            entradas=0,
            salidas=2,
            entradas_csf11=0,
            salidas_csf11=1,
            entradas_csf21=0,
            salidas_csf21=0,
            entradas_chs01=0,
            salidas_chs01=1,
        ),
    ]
    caps_sector = {"CSF11": 40, "CSF21": 50, "CHS01": 35, "todos": 125}
    curva_veh = _calcular_curva_presencia_vehicular_por_hora(sesiones_veh, flujo_veh, ahora_ref, caps_sector, 125)
    pico_veh_08 = next(p for p in curva_veh if p["bucket"].endswith("08:00:00"))
    pico_veh_09 = next(p for p in curva_veh if p["bucket"].endswith("09:00:00"))

    # 4. Fixture controlado para VehicleService.get_kpis
    fila_veh_g = SimpleNamespace(
        vehiculos_unicos=4,
        total_entradas=3,
        total_salidas=3,
        total_accesos_csf11=1,
        total_accesos_csf21=1,
        total_accesos_chs01=1,
        dias_operativos=1,
        tasa_lectura_fallida_pct=0.0,
        hora_punta_num=8,
        max_entradas=3,
    )
    fila_veh_p = SimpleNamespace(permanencia_mediana_min=45.0)
    db_veh = _crear_sesion_mock_filas([fila_veh_g, fila_veh_p])
    with (
        patch.object(VehicleService, "_build_vehicle_filters", new=AsyncMock(return_value=("1=1", {}))),
        patch("app.services.vehicle_service._obtener_capacidades_sectores_vehiculares", new=AsyncMock(return_value=caps_sector)),
        patch.object(VehicleService, "get_realtime_presence_curve", new=AsyncMock(return_value=curva_veh)),
    ):
        kpis_veh = await VehicleService.get_kpis(db_veh, espacio_id=2, fecha_inicio=fecha_ev, fecha_fin=fecha_ev)

    return [
        ("AttendanceService (Presencia 10h)", "Pico simultáneo global", 3.0, float(pico_bib_10["personas_unicas"])),
        ("AttendanceService (Presencia 10h)", "Pico simultáneo Sala 1", 2.0, float(pico_bib_10["personas_sala1"])),
        ("AttendanceService (Presencia 11h)", "Arrastre continuo Sala 2", 1.0, float(pico_bib_11["personas_unicas"])),
        ("AttendanceService (KPIs)", "Total registros", 3.0, float(kpis_bib["total_registros"])),
        ("AttendanceService (KPIs)", "Horas estudiante total", 3.0, float(kpis_bib["horas_estudiante_total"])),
        ("AttendanceService (KPIs)", "Ocupación pico curva", 3.0, float(kpis_bib["max_aforo_historico"])),
        ("VehicleService (Presencia 08h)", "Vehículos simultáneos total", 3.0, float(pico_veh_08["vehiculos_presentes"])),
        ("VehicleService (Presencia 09h)", "Arrastre vehicular CSF11+CHS01", 2.0, float(pico_veh_09["vehiculos_presentes"])),
        ("VehicleService (KPIs)", "Vehículos únicos", 4.0, float(kpis_veh["vehiculos_unicos"])),
        ("VehicleService (KPIs)", "Total accesos (entradas)", 3.0, float(kpis_veh["total_accesos"])),
        ("VehicleService (KPIs)", "Pico simultáneo vehicular", 3.0, float(kpis_veh["max_aforo_historico"])),
    ]


def ejecutar_auditoria() -> list[tuple[str, str, float, float]]:
    filas = asyncio.run(_auditar_servicios())
    print("\n" + "=" * 105)
    print("MATRIZ DE CONCILIACIÓN MATEMÁTICA — FIXTURE CONTROLADO VS SERVICIOS REALES")
    print("=" * 105)
    print(f"{'Servicio / Caso':<36} | {'Métrica Analítica':<32} | {'Esperado':<10} | {'Servicio':<10} | {'Error':<8}")
    print("-" * 105)

    max_delta_pct = 0.0
    for servicio, metrica, esperado, obtenido in filas:
        delta = abs(obtenido - esperado)
        pct = (delta / esperado * 100.0) if esperado != 0 else 0.0
        max_delta_pct = max(max_delta_pct, pct)
        print(f"{servicio:<36} | {metrica:<32} | {esperado:<10.2f} | {obtenido:<10.2f} | {pct:.2f}%")
        assert pct == 0.0, f"Discrepancia detectada en {servicio} -> {metrica}: esperado={esperado}, obtenido={obtenido}"

    print("-" * 105)
    print(f"DISCREPANCIA MÁXIMA OBSERVADA: {max_delta_pct:.2f}%")
    print("DICTAMEN: CONCILIACIÓN CERTIFICADA AL 100.00% (0.00% ERROR)")
    print("=" * 105 + "\n")
    return filas


if __name__ == "__main__":
    ejecutar_auditoria()
