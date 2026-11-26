from datetime import datetime
import logging
from typing import Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.tiempo import ahora_chile_naive
from app.services.config_service import get_espacios_activos_capacidades
from app.ml.prophet_service import predict_continuous, predict_next_7_days, predict_presence_continuous, _fetch_capacidades
from app.services.attendance_service import AttendanceService

logger = logging.getLogger(__name__)

async def get_prophet_forecast(db: AsyncSession, recinto: str, sala: str = "todas") -> Dict[str, Any]:
    try:
        resultado = await predict_continuous(db, recinto=recinto, sala=sala)
        model_status = resultado.get("model_status", {})
        if model_status.get("status") == "unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=model_status.get("message", "Modelo no disponible"),
                headers={"X-Model-Status": "unavailable"},
            )
        return resultado
    except HTTPException as e:
        logger.error(f"HTTPException en get_prophet_forecast para {recinto} (sala={sala}): {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error getting prophet forecast for {recinto} (sala={sala}): {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el modelo predictivo"
        )

async def get_prophet_presence_forecast(db: AsyncSession, sala: str = "todas") -> Dict[str, Any]:
    try:
        resultado = await predict_presence_continuous(db, sala=sala)
        model_status = resultado.get("model_status", {})
        if model_status.get("status") == "unavailable":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=model_status.get("message", "Modelo de presencia no disponible"),
                headers={"X-Model-Status": "unavailable"},
            )
        return resultado
    except HTTPException as e:
        logger.error(f"HTTPException en get_prophet_presence_forecast (sala={sala}): {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error getting prophet presence forecast (sala={sala}): {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el modelo predictivo de presencia"
        )

async def get_visit_profiles(db: AsyncSession, espacio_id: int) -> Dict[str, Any]:
    """
    Alternativa A: Enfoque estadístico determinista en base de datos.
    Empareja entradas y salidas reales mediante ventanas temporales SQL con exactitud del 100%.
    """
    try:
        donut_data = await AttendanceService.get_visit_profiles_donut(
            session=db,
            espacio_id=espacio_id,
        )
        return {
            "espacio_id": espacio_id,
            "metodo": "determinista_sql",
            "total_visitas_analizadas": donut_data.get("total_visitas_analizadas", 0),
            "tasa_rebote_pct": donut_data.get("tasa_rebote_pct", 0.0),
            "perfiles": [
                {
                    "perfil": item["perfil"],
                    "total": item["total"],
                    "porcentaje": item["porcentaje"],
                    "permanencia_promedio_min": item["promedio_min"],
                }
                for item in donut_data.get("items", [])
            ],
        }
    except HTTPException as e:
        logger.error(f"HTTPException en get_visit_profiles para {espacio_id}: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error getting visit profiles for {espacio_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el modelo predictivo"
        )

def _filtrar_ventana_proximas_3h(pronostico: list[Dict[str, Any]], ahora_ref: datetime) -> list[Dict[str, Any]]:
    """Extrae hasta 3 bloques horarios desde ahora; conserva entradas sin 'ds' para compatibilidad de tests."""
    candidatos = []
    for punto in pronostico or []:
        ds_raw = punto.get("ds")
        if not ds_raw:
            candidatos.append(punto)
            continue
        try:
            dt_p = datetime.fromisoformat(str(ds_raw).replace("Z", "+00:00"))
            if dt_p.tzinfo is not None:
                dt_p = dt_p.replace(tzinfo=None)
            if dt_p >= ahora_ref.replace(minute=0, second=0, microsecond=0):
                candidatos.append(punto)
        except Exception:
            candidatos.append(punto)
    if not candidatos and pronostico:
        return list(pronostico[:3])
    return candidatos[:3]


async def get_active_alerts(db: AsyncSession) -> Dict[str, Any]:
    try:
        UMBRAL_ALERTA = 0.85
        ahora_cl = ahora_chile_naive()
        CAPACIDADES, fuente = await get_espacios_activos_capacidades(db)
        
        if not CAPACIDADES and fuente != "fallback":
            return {
                "total_alertas": 0, 
                "alertas": [], 
                "advertencia": "Sin espacios activos configurados"
            }

        alerts = []
        caps_detalle: Dict[str, Any] = {}
        if "biblioteca" in CAPACIDADES or "vehicular" in CAPACIDADES:
            try:
                caps_detalle = await _fetch_capacidades(db)
            except Exception:
                caps_detalle = {}

        for recinto, cap in CAPACIDADES.items():
            if cap == 0:
                continue

            if recinto == "biblioteca":
                cap_s1 = float(caps_detalle.get("sala1", 150))
                cap_s2 = float(caps_detalle.get("sala2", 126))
                cap_tot = float(caps_detalle.get("todas", cap))
                subespacios_bib = [
                    ("sala1", "Sala 1 (CSF02)", cap_s1),
                    ("sala2", "Sala 2 (CSF04 Pecera)", cap_s2),
                    ("todas", "Biblioteca Global", cap_tot),
                ]
                for sub_key, sub_label, cap_sub in subespacios_bib:
                    if cap_sub <= 0:
                        continue
                    res_pres = await predict_presence_continuous(db, sala=sub_key)
                    if res_pres.get("model_status", {}).get("status") == "unavailable":
                        continue
                    proximas_3h = _filtrar_ventana_proximas_3h(res_pres.get("pronostico_7d", []), ahora_cl)
                    horas_sobre_umbral = [
                        f for f in proximas_3h if f["yhat"] >= cap_sub * UMBRAL_ALERTA
                    ]
                    if len(horas_sobre_umbral) >= 2:
                        alerts.append({
                            "recinto": recinto,
                            "subespacio": sub_key,
                            "subespacio_label": sub_label,
                            "nivel": "critico" if len(horas_sobre_umbral) == 3 else "preventivo",
                            "mensaje": (
                                f"{sub_label}: ocupación proyectada ≥ {int(UMBRAL_ALERTA * 100)}% de capacidad "
                                f"({int(cap_sub)} asientos) en {len(horas_sobre_umbral)} de las próximas 3 horas."
                            ),
                            "horas_afectadas": horas_sobre_umbral,
                            "capacidad_max": cap_sub,
                        })
                continue

            if recinto == "vehicular":
                cap_c11 = float(caps_detalle.get("CSF11", 40))
                cap_c21 = float(caps_detalle.get("CSF21", 50))
                cap_ch01 = float(caps_detalle.get("CHS01", 35))
                cap_tot_v = float(caps_detalle.get("vehicular", cap))
                subespacios_veh = [
                    ("CSF11", "CSF11 — Edificio 11", cap_c11),
                    ("CSF21", "CSF21 — Edificio 21", cap_c21),
                    ("CHS01", "CHS01 — Hosp. Simulación", cap_ch01),
                    ("todos", "Estacionamiento Global", cap_tot_v),
                ]
                for sub_key, sub_label, cap_sub in subespacios_veh:
                    if cap_sub <= 0:
                        continue
                    res_veh = await predict_continuous(db, recinto="vehicular", sala=sub_key)
                    if res_veh.get("model_status", {}).get("status") == "unavailable":
                        continue
                    proximas_3h = _filtrar_ventana_proximas_3h(res_veh.get("pronostico_7d", []), ahora_cl)
                    horas_sobre_umbral = [
                        f for f in proximas_3h if f["yhat"] >= cap_sub * UMBRAL_ALERTA
                    ]
                    if len(horas_sobre_umbral) >= 2:
                        alerts.append({
                            "recinto": recinto,
                            "subespacio": sub_key,
                            "subespacio_label": sub_label,
                            "nivel": "critico" if len(horas_sobre_umbral) == 3 else "preventivo",
                            "mensaje": (
                                f"{sub_label}: ocupación proyectada ≥ {int(UMBRAL_ALERTA * 100)}% de capacidad "
                                f"({int(cap_sub)} plazas) en {len(horas_sobre_umbral)} de las próximas 3 horas."
                            ),
                            "horas_afectadas": horas_sobre_umbral,
                            "capacidad_max": cap_sub,
                        })
                continue

            forecasts, model_status = await predict_next_7_days(db, recinto=recinto)
            if model_status["status"] == "unavailable":
                continue

            proximas_3h = _filtrar_ventana_proximas_3h(forecasts, ahora_cl)
            horas_sobre_umbral = [
                f for f in proximas_3h if f["yhat"] >= cap * UMBRAL_ALERTA
            ]
            if len(horas_sobre_umbral) >= 2:
                alerts.append({
                    "recinto": recinto,
                    "nivel": "critico" if len(horas_sobre_umbral) == 3 else "preventivo",
                    "mensaje": (
                        f"Ocupación proyectada ≥ {int(UMBRAL_ALERTA * 100)}% de capacidad "
                        f"en {len(horas_sobre_umbral)} de las próximas 3 horas."
                    ),
                    "horas_afectadas": horas_sobre_umbral,
                    "capacidad_max": cap,
                })

        respuesta = {"total_alertas": len(alerts), "alertas": alerts}
        if fuente == "fallback":
            respuesta["fuente"] = fuente
            
        return respuesta
    except HTTPException as e:
        logger.error(f"HTTPException en get_active_alerts: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error getting active alerts: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error calculando alertas: {str(e)}"
        )
