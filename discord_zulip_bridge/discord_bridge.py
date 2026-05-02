from __future__ import annotations

import asyncio

import discord


class DiscordBridgeClient(discord.Client):
    def __init__(
        self,
        *,
        text_channel_id: int,
        forum_channel_id: int,
        on_text_message,
        on_forum_message,
        ready_event: asyncio.Event,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._text_channel_id = text_channel_id
        self._forum_channel_id = forum_channel_id
        self._on_text_message = on_text_message
        self._on_forum_message = on_forum_message
        self._ready_event = ready_event

    async def on_ready(self) -> None:
        user = self.user
        if user is None:
            print("Connected to Discord")
        else:
            print(f"Connected to Discord as {user} (id={user.id})")
        self._ready_event.set()

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.channel.id == self._text_channel_id:
            await self._on_text_message(message)
            return
        parent_id = getattr(message.channel, "parent_id", None)
        if parent_id == self._forum_channel_id:
            await self._on_forum_message(message)
