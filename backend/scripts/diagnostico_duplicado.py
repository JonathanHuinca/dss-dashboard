import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as s:
        r = await s.execute(text("SELECT time, espacio_id, person_id_hash FROM eventos_asistencia WHERE person_id_hash = '886d538eb0fe35b93c3cb4d2652dd367103e650ddde24d1f1dc1fe91a2ecffe8'"))
        rows = r.fetchall()
        print(f"Total rows for 886d... in DB: {len(rows)}")
        for row in rows:
            print(f"  DB: {row}")

if __name__ == "__main__":
    asyncio.run(main())
