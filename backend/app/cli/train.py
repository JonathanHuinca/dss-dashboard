"""
train.py — Comando CLI para entrenamiento de modelos con orquestador Campeón vs. Retador.

Uso:
    python -m app.cli entrenar-modelos
"""
import asyncio
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.database import AsyncSessionLocal
from app.ml.orquestador_entrenamiento import entrenar_todos_los_modelos


async def train() -> None:
    solo_operativos_hoy = "--solo-operativos-hoy" in sys.argv
    print("\n========================================================")
    print("       UCT DSS — Orquestador de Modelos ML             ")
    print("       Evaluación y Promoción: Campeón vs. Retador     ")
    print("========================================================\n")

    async with AsyncSessionLocal() as session:
        results = await entrenar_todos_los_modelos(
            session,
            solo_modulos_operativos_hoy=solo_operativos_hoy,
        )

    print("\n+--------------------------------------------------------------------------------+")
    print("|                  REPORTE DE ENTRENAMIENTO CAMPEÓN vs. RETADOR                   |")
    print("+--------------------------------------------------------------------------------+")
    for r in results:
        modelo = r.get("modelo", "")
        estado = r.get("estado", "").upper()
        if estado == "PROMOVIDO":
            w = r.get("wape", 0)
            m = r.get("mae", 0)
            prev = r.get("campeon_anterior_wape", "N/A")
            print(f"| [PROMOVIDO] {modelo:<28} WAPE={w}% (ant: {prev}%) | MAE={m}")
        elif estado == "RECHAZADO":
            motivo = r.get("motivo", "")[:45]
            print(f"| [RECHAZADO] {modelo:<28} {motivo}")
        elif estado == "OMITIDO_DIA_NO_LABORAL":
            motivo = r.get("motivo", "")[:45]
            print(f"| [OMITIDO]   {modelo:<28} {motivo}")
        else:
            err = r.get("error", "Error desconocido")[:45]
            print(f"| [CONSERVADO]{modelo:<28} Campeón conservado ({err})")
    print("+--------------------------------------------------------------------------------+\n")
    print(f"__RESULTADO_JSON__:{json.dumps(results, ensure_ascii=False)}")



def main_train():
    asyncio.run(train())
