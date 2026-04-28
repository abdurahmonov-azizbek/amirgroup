import json
import logging
from typing import Any, Dict, Optional

from aiogram.fsm.storage.base import BaseStorage, StorageKey
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import insert

from database.models import FSMState
from database.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

class SQLAlchemyStorage(BaseStorage):
    async def set_state(self, key: StorageKey, state: Optional[str] = None) -> None:
        try:
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
                logger.info(f"FSM State set: {key.user_id} -> {state}")
        except Exception as e:
            logger.error(f"FSM set_state error: {e}")

    async def get_state(self, key: StorageKey) -> Optional[str]:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(FSMState.state).where(
                        FSMState.user_id == key.user_id,
                        FSMState.chat_id == key.chat_id
                    )
                )
                val = result.scalar_one_or_none()
                logger.info(f"FSM State get: {key.user_id} -> {val}")
                return val
        except Exception as e:
            logger.error(f"FSM get_state error: {e}")
            return None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        try:
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
        except Exception as e:
            logger.error(f"FSM set_data error: {e}")

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(FSMState.data).where(
                        FSMState.user_id == key.user_id,
                        FSMState.chat_id == key.chat_id
                    )
                )
                data_json = result.scalar_one_or_none()
                return json.loads(data_json) if data_json else {}
        except Exception as e:
            logger.error(f"FSM get_data error: {e}")
            return {}

    async def close(self) -> None:
        pass
