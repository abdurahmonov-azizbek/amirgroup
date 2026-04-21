from sqlalchemy.future import select
from database.session import AsyncSessionLocal
from database.models import Config

async def get_config(key: str, default: str = None) -> str:
    """
    Fetch a value from the Configs table asynchronously.
    Returns the string value if found, otherwise returns the default value.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Config).where(Config.key == key))
            cfg = result.scalar_one_or_none()
            if cfg:
                return cfg.value
    except Exception as e:
        print(f"Error fetching config '{key}' from DB: {e}")
        
    return default
