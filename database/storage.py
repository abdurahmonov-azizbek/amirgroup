import json
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert

from database.models import FSMState
from database.session import AsyncSessionLocal

class SQLAlchemyStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: Optional[str] = None) -> None:
        async with AsyncSessionLocal() as session:
            stmt = insert(FSMState).values(
                user_id=key.user_id,
                chat_id=key.chat_id,
                state=state,
                data="{}"
            ).on_conflict_do_update(
                index_elements=['user_id', 'chat_id'],
                set_={'state': state}
            )
            await session.execute(stmt)
            await session.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FSMState.state).where(
                    FSMState.user_id == key.user_id,
                    FSMState.chat_id == key.chat_id
                )
            )
            return result.scalar_one_or_none()

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        async with AsyncSessionLocal() as session:
            data_json = json.dumps(data)
            stmt = insert(FSMState).values(
                user_id=key.user_id,
                chat_id=key.chat_id,
                state=None,
                data=data_json
            ).on_conflict_do_update(
                index_elements=['user_id', 'chat_id'],
                set_={'data': data_json}
            )
            await session.execute(stmt)
            await session.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(FSMState.data).where(
                    FSMState.user_id == key.user_id,
                    FSMState.chat_id == key.chat_id
                )
            )
            data_json = result.scalar_one_or_none()
            return json.loads(data_json) if data_json else {}

    async def close(self) -> None:
        pass
