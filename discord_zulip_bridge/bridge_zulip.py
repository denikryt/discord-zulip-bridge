from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class ZulipMessage:
    message_id: int
    sender_email: str
    sender_full_name: str
    stream: str
    topic: str
    content: str


class ZulipBridge:
    def __init__(self, site: str, bot_email: str, api_key: str) -> None:
        self._site = site.rstrip("/")
        self._bot_email = bot_email
        self._client = httpx.AsyncClient(
            base_url=f"{self._site}/api/v1",
            auth=(bot_email, api_key),
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"User-Agent": "discord-zulip-bridge/0.1"},
        )
        self._queue_id: str | None = None
        self._last_event_id = -1
        self._event_timeout = 60
        self._bot_user_id: int | None = None
        self._max_message_length: int | None = None

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_own_user(self) -> dict[str, Any]:
        response = await self._client.get("/users/me")
        response.raise_for_status()
        return response.json()

    async def ensure_subscribed(self, stream_name: str) -> None:
        payload = {"subscriptions": json.dumps([{"name": stream_name}])}
        response = await self._client.post("/users/me/subscriptions", data=payload)
        response.raise_for_status()

    async def register_queue(self, stream_name: str) -> dict[str, Any]:
        payload = {
            "event_types": json.dumps(["message"]),
            "narrow": json.dumps([["channel", stream_name]]),
        }
        response = await self._client.post("/register", data=payload)
        response.raise_for_status()
        data = response.json()
        self._queue_id = data["queue_id"]
        self._last_event_id = data["last_event_id"]
        self._event_timeout = int(data.get("event_queue_longpoll_timeout_seconds", 60))
        max_message_length = data.get("max_message_length")
        if isinstance(max_message_length, int):
            self._max_message_length = max_message_length
        return data

    async def initialize(self, stream_name: str) -> None:
        await self.ensure_subscribed(stream_name)
        profile = await self.get_own_user()
        self._bot_user_id = profile["user_id"]
        await self.register_queue(stream_name)

    async def send_message(self, stream: str, topic: str, content: str) -> dict[str, Any]:
        if self._max_message_length is not None and len(content) > self._max_message_length:
            content = content[: self._max_message_length - 32] + "\n\n[message truncated by bridge]"
        payload = {
            "type": "stream",
            "to": stream,
            "topic": topic,
            "content": content,
        }
        response = await self._client.post("/messages", data=payload)
        response.raise_for_status()
        return response.json()

    async def poll_events(self) -> list[ZulipMessage]:
        if self._queue_id is None:
            raise RuntimeError("Zulip queue is not registered")

        response = await self._client.get(
            "/events",
            params={"queue_id": self._queue_id, "last_event_id": self._last_event_id},
            timeout=httpx.Timeout(self._event_timeout + 10, connect=10.0),
        )
        response.raise_for_status()
        data = response.json()
        self._queue_id = data.get("queue_id", self._queue_id)

        messages: list[ZulipMessage] = []
        for event in data.get("events", []):
            event_id = event.get("id")
            if isinstance(event_id, int) and event_id > self._last_event_id:
                self._last_event_id = event_id
            if event.get("type") != "message":
                continue
            message = event.get("message")
            if not isinstance(message, dict):
                continue
            if message.get("type") != "stream":
                continue
            sender_email = str(message.get("sender_email", ""))
            sender_id = message.get("sender_id")
            if sender_email == self._bot_email:
                continue
            if self._bot_user_id is not None and sender_id == self._bot_user_id:
                continue
            messages.append(
                ZulipMessage(
                    message_id=int(message["id"]),
                    sender_email=sender_email,
                    sender_full_name=str(message.get("sender_full_name", sender_email)),
                    stream=str(message.get("display_recipient", "")),
                    topic=str(message.get("subject", "")),
                    content=str(message.get("content", "")),
                )
            )
        return messages

    async def run_event_loop(self, stream_name: str, handler, ready_event: asyncio.Event | None = None) -> None:
        while True:
            try:
                if self._queue_id is None:
                    await self.initialize(stream_name)
                    if ready_event is not None:
                        ready_event.set()
                for message in await self.poll_events():
                    if message.stream != stream_name:
                        continue
                    await handler(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._queue_id = None
                await asyncio.sleep(5)
