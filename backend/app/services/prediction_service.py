import logging
from typing import Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.config_service import get_espacios_activos_capacidades
from app.ml.prophet_service import predict_continuous, predict_next_7_days
from app.ml.train_gbr_demand import predict_next_14_days
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

async def get_gbr_forecast_14days(db: AsyncSession, espacio_id: int) -> Dict[str, Any]:
    try:
        result = await predict_next_14_days(db, espacio_id=espacio_id)
        return result
    except HTTPException as e:
        logger.error(f"HTTPException en get_gbr_forecast_14days para {espacio_id}: {e.detail}")
        raise
    except Exception as e:
        logger.error(f"Error getting GBR 14 days forecast for {espacio_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno al procesar el modelo predictivo"
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

async def get_active_alerts(db: AsyncSession) -> Dict[str, Any]:
    try:
        UMBRAL_ALERTA = 0.85
        CAPACIDADES, fuente = await get_espacios_activos_capacidades(db)
        
        if not CAPACIDADES and fuente != "fallback":
            return {
                "total_alertas": 0, 
                "alertas": [], 
                "advertencia": "Sin espacios activos configurados"
            }

        alerts = []
        for recinto, cap in CAPACIDADES.items():
            if cap == 0:
                continue
                
            forecasts, model_status = await predict_next_7_days(db, recinto=recinto)
            if model_status["status"] == "unavailable":
                continue

            proximas_3h = forecasts[:3]
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
