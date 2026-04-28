import asyncio
from database.session import engine
from database.models import Base

async def init_models():
    async with engine.begin() as conn:
        # Faqat mavjud bo'lmagan jadvallarni yaratadi
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables initialized!")

if __name__ == "__main__":
    asyncio.run(init_models())
