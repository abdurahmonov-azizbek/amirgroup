import aiohttp
import json as json_lib
from aiohttp import BasicAuth
from services.config_db import get_config
from typing import Dict, Any, Optional


class OneCClient:

    async def _get_auth(self):
        db_url = await get_config("one_c_url", "")
        db_login = await get_config("one_c_login", "")
        db_pass = await get_config("one_c_pass", "")
        base_url = db_url.rstrip("/") if db_url else ""
        auth = BasicAuth(login=db_login, password=db_pass) if db_login else None
        return base_url, auth

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        base_url, auth = await self._get_auth()
        url = f"{base_url}/{endpoint.lstrip('/')}"

        async with aiohttp.ClientSession(auth=auth) as session:
            try:
                async with session.request(method, url, **kwargs) as response:
                    raw_text = await response.text()

                    if response.status == 200:
                        # 1C ba'zan JSON content-type bermaydi — to'g'ridan-to'g'ri parse qilamiz
                        try:
                            return json_lib.loads(raw_text)
                        except json_lib.JSONDecodeError:
                            print(f"1C API JSON parse error. Status=200 but got: {raw_text[:200]}")
                            return None

                    elif response.status == 404:
                        # Mijoz topilmadi — normal holat
                        print(f"1C API: 404 Not Found — {url}")
                        return None

                    else:
                        print(f"1C API Error: {response.status} — {raw_text[:200]}")
                        return None

            except Exception as e:
                print(f"1C API Connection Error: {e}")
                return None

    async def check_user(self, phone: str) -> Optional[Dict[str, Any]]:
        """
        Telefon raqami bo'yicha 1C dan mijoz ma'lumotlarini olish.
        Format: 998901234567
        """
        # Telefon raqamni normallashtirish (+ olib tashlash)
        phone = phone.lstrip("+").strip()
        return await self._request("GET", f"/check_user/{phone}")

    async def get_client_data(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        1C UUID bo'yicha mijoz ma'lumotlarini olish.
        """
        return await self._request("GET", f"/get_client_data/{client_id}")


# Singleton instance
one_c = OneCClient()
