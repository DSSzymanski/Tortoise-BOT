import os
import json
import logging
from typing import Optional, List, Union
from datetime import datetime, timezone

import aiohttp
from dotenv import load_dotenv
from discord import Member, Message

from bot.constants import SuggestionStatus


load_dotenv()  # TODO why here also? in main too
logger = logging.getLogger(__name__)


class ResponseCodeError(ValueError):
    """Raised when a non-OK HTTP response is received."""

    def __init__(
        self,
        response: aiohttp.ClientResponse,
        response_json: Optional[dict] = None,
        response_text: str = ""
    ):
        self.status = response.status
        self.response_json = response_json or {}
        self.response_text = response_text
        self.response = response

    def __str__(self):
        response = self.response_json if self.response_json else self.response_text
        return f"Status: {self.status} Response: {response}"


class APIClient:
    def __init__(self, loop):
        self.auth_header = {"Authorization": f"Token {os.getenv('API_ACCESS_TOKEN')}"}
        self.session = aiohttp.ClientSession(loop=loop, headers=self.auth_header)

    @staticmethod
    def _url_for(endpoint: str) -> str:
        return f"https://api.tortoisecommunity.ml/private/{endpoint}"

    @classmethod
    async def raise_for_status(cls, response: aiohttp.ClientResponse) -> None:
        """Raise ResponseCodeError for non-OK response if an exception should be raised."""
        if response.status >= 400:
            try:
                response_json = await response.json()
                raise ResponseCodeError(response=response, response_json=response_json)
            except aiohttp.ContentTypeError:
                response_text = await response.text()
                raise ResponseCodeError(response=response, response_text=response_text)

    async def get(self, endpoint: str, **kwargs) -> Union[dict, List[dict]]:
        async with self.session.get(self._url_for(endpoint), **kwargs) as resp:
            await self.raise_for_status(resp)
            return await resp.json()

    async def patch(self, endpoint: str, **kwargs) -> dict:
        async with self.session.patch(self._url_for(endpoint), **kwargs) as resp:
            await self.raise_for_status(resp)
            return await resp.json()

    async def post(self, endpoint: str, **kwargs) -> dict:
        async with self.session.post(self._url_for(endpoint), **kwargs) as resp:
            await self.raise_for_status(resp)
            return await resp.json()

    async def put(self, endpoint: str, **kwargs) -> dict:
        async with self.session.put(self._url_for(endpoint), **kwargs) as resp:
            await self.raise_for_status(resp)
            return await resp.json()

    async def delete(self, endpoint: str, **kwargs) -> Optional[dict]:
        async with self.session.delete(self._url_for(endpoint), **kwargs) as resp:
            if resp.status == 204:
                return

            await self.raise_for_status(resp)
            return await resp.json()


class TortoiseAPI(APIClient):
    def __init__(self, loop):
        super().__init__(loop)

    async def does_member_exist(self, member_id: int) -> bool:
        try:
            await self.is_verified(member_id, re_raise=True)
            return True
        except ResponseCodeError:
            return False

    async def is_verified(self, member_id: int, *, re_raise=False) -> bool:
        """
        "verify-confirmation/{member_id}/" endpoint return format {'verified': True} or 404 status
        :param member_id: int member id
        :param re_raise: bool whether to re-raise ResponseCodeError if member_id is not found.
        :return: bool
        """
        # Endpoint return format {'verified': True} or 404 status
        try:
            data = await self.get(f"verify-confirmation/{member_id}/")
        except ResponseCodeError as e:
            if re_raise:
                raise e
            else:
                return False
        return data["verified"]

    async def insert_new_member(self, member: Member):
        """For inserting new members in the database."""
        data = {
            "user_id": member.id,
            "guild_id": member.guild.id,
            "join_date": datetime.now(timezone.utc).isoformat(),
            "name": member.display_name,
            "tag": member.discriminator,
            "member": True
        }
        await self.post("members/", json=data)

    async def member_rejoined(self, member: Member):
        data = {"user_id": member.id, "guild_id": member.guild.id, "member": True, "leave_date": None}
        await self.put(f"members/edit/{member.id}/", json=data)

    async def member_left(self, member: Member):
        data = {
            "user_id": member.id,
            "guild_id": member.guild.id,
            "leave_date": datetime.now(timezone.utc).isoformat(),
            "member": False
        }
        await self.put(f"members/edit/{member.id}/", json=data)

    async def get_member_roles(self, member_id: int) -> List[int]:
        # Endpoint return format {'roles': [int...]} or 404 status
        data = await self.get(f"members/{member_id}/roles/")
        return data["roles"]

    async def get_member_data(self, member_id: int) -> dict:
        return await self.get(f"members/edit/{member_id}/")

    async def get_all_members(self) -> list:
        return await self.get("members/")

    async def edit_member_roles(self, member: Member, roles_ids: List[int]):
        await self.put(
            f"members/edit/{member.id}/",
            json={
                "user_id": member.id,
                "guild_id": member.guild.id,
                "roles": roles_ids
            }
        )

    async def get_all_rules(self) -> List[dict]:
        """
        Return format:
        [
          {"number": 1,
          "alias": ["tos", "guidelines", "terms"],
          "statement": "Follow the Discord Community Guidelines and Terms Of Service."
          },
          ...
        ]
        """
        return await self.get("rules/")

    async def get_all_suggestions(self) -> List[dict]:
        return await self.get("suggestions/")

    async def get_suggestion(self, suggestion_id: int) -> dict:
        return await self.get(f"suggestions/{suggestion_id}/")

    async def post_suggestion(self, author: Member, message: Message, suggestion: str):
        data = {
            "message_id": message.id,
            "author_id": author.id,
            "author_name": author.display_name,
            "brief": suggestion,
            "avatar": str(author.avatar_url),
            "link": message.jump_url,
            "date": datetime.now(timezone.utc).isoformat()
        }
        await self.post("suggestions/", json=data)

    async def put_suggestion(self, suggestion_id: int, status: SuggestionStatus, reason: str):
        data = {"status": status.value, "reason": reason}
        await self.put(f"suggestions/{suggestion_id}/", json=data)

    async def delete_suggestion(self, suggestion_id: int):
        await self.delete(f"suggestions/{suggestion_id}/")

    async def get_member_meta(self, member_id: int) -> dict:
        """
        Return type:
        {
            "warnings": [],
            "muted_until": null,
            "strikes": {
                "AD": 0,
                "Homo": 0,
                "Common": 0,
                "Racial": 0
            },
            "mod_mail": true,
            "perks": 300
        }
        """
        return await self.get(f"member/meta/{member_id}/")

    async def get_member_warnings(self, member_id: int) -> List[dict]:
        """
        API returns a list of str (which are stringed dicts) so need to deserialize that.
        Example return from API:
        [
            '{"date": "2020-05-04T21:36:43.045204+00:00",
            "reason": "test",
            "mod": 197918569894379520}'
        ]
        """
        member_meta = await self.get_member_meta(member_id)
        warnings = member_meta["warnings"]
        deserialized_warnings = [json.loads(item) for item in warnings]
        return deserialized_warnings

    async def get_member_warnings_count(self, member_id: int) -> int:
        return len(await self.get_member_warnings(member_id))

    async def add_member_warning(self, mod_id: int, member_id: id, reason: str):
        new_warning = {
            "mod": mod_id,
            "reason": reason,
            "date": datetime.now(timezone.utc).isoformat()
        }

        current_warnings = await self.get_member_warnings(member_id)
        current_warnings.append(json.dumps(new_warning))

        warnings_payload = {"warnings": current_warnings}

        await self.put(f"member/meta/{member_id}/", json=warnings_payload)
