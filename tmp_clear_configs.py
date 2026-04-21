import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from database.session import AsyncSessionLocal
from database.models import Config
from sqlalchemy import delete

async def clear_configs():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Config))
        await session.commit()
        print("Configs table cleared.")

if __name__ == "__main__":
    asyncio.run(clear_configs())
