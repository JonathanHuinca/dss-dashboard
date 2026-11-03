import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text
from app.core.database import AsyncSessionLocal

async def fix():
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(text("ALTER TABLE ingestion_jobs DROP CONSTRAINT ck_ij_tipo"))
            print("Dropped ck_ij_tipo")
        except Exception as e:
            print(f"Drop error (might not exist): {e}")

        await session.execute(text("ALTER TABLE ingestion_jobs ADD CONSTRAINT ck_ij_tipo CHECK (tipo IN ('asistencia', 'marcajes_torniquete', 'vehicular', 'vehicular_anpr', 'academico', 'curricular', 'custom'))"))
        await session.commit()
        print("Constraint ck_ij_tipo successfully updated to include 'marcajes_torniquete' and 'vehicular_anpr'!")

if __name__ == "__main__":
    asyncio.run(fix())
