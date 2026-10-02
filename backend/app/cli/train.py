"""
train.py — Comando CLI para entrenamiento inicial de modelos Prophet.

Uso:
    cd backend/
    python -m app.cli train-models

Extrae los datos de los Continuous Aggregates de TimescaleDB,
entrena Prophet para biblioteca y vehicular, evalúa métricas
y serializa los modelos en backend/models/.
"""
import asyncio
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.core.database import AsyncSessionLocal
from app.ml.prophet_service import train_all


async def train() -> None:
    print("\n========================================================")
    print("       UCT Dashboard -- Entrenamiento Prophet")
    print("========================================================\n")

    async with AsyncSessionLocal() as session:
        results = await train_all(session)

    print("\n+------------------------------------------------------+")
    print("|              RESULTADO DE ENTRENAMIENTO              |")
    print("+------------------------------------------------------+")
    for r in results:
        if "error" in r:
            print(f"|  [X] {r['recinto']:<12} ERROR: {r['error'][:38]}")
        else:
            wape_str = f"{r['wape']}%" if r["wape"] is not None else "N/A (denominador=0)"
            base_str = f"{r['wape_baseline']}%" if r["wape_baseline"] is not None else "N/A"
            print(f"|  [OK] {r['recinto']:<11} WAPE={wape_str:<10}  MAE={r['mae']:.2f}")
            print(f"|  {'':14} WAPE Baseline={base_str:<10}  Rows={r['train_rows']}+{r['test_rows']}")
    print("+------------------------------------------------------+\n")
    print("[OK] Modelos serializados en backend/models/")
    print("  prophet_biblioteca_active.joblib")
    print("  prophet_vehicular_active.joblib\n")


def main_train():
    if len(sys.argv) < 2 or sys.argv[1] != "train-models":
        print("Uso: python -m app.cli train-models")
        sys.exit(1)
    asyncio.run(train())
