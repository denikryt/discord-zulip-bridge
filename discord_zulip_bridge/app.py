from __future__ import annotations

import asyncio

import discord

from .config import Settings
from .discord_bridge import DiscordBridgeClient
from .zulip_bridge import ZulipBridge, ZulipMessage


def _format_discord_to_zulip(settings: Settings, message: discord.Message) -> str:
    parts: list[str] = []
    parts.append(f"{settings.discord_activity_prefix} **{message.author.display_name}**")
    parts.append(f"Channel: <#{message.channel.id}>")
    parts.append("")
    parts.append(message.content or "_No text content_")
    if message.attachments:
        parts.append("")
        parts.append("Attachments:")
        for attachment in message.attachments:
            parts.append(f"- {attachment.url}")
    parts.append("")
    parts.append(f"Discord message: {message.jump_url}")
    return "\n".join(parts)


def _format_zulip_to_discord(settings: Settings, message: ZulipMessage) -> str:
    parts: list[str] = []
    parts.append(f"{settings.zulip_activity_prefix} **{message.sender_full_name}**")
    parts.append(f"Stream: `{message.stream}` | Topic: `{message.topic}`")
    parts.append("")
    parts.append(message.content or "_No text content_")
    return "\n".join(parts)


async def run() -> None:
    settings = Settings.load()
    zulip = ZulipBridge(
        site=settings.zulip_site,
        bot_email=settings.zulip_bot_email,
        api_key=settings.zulip_api_key,
    )

    discord_ready = asyncio.Event()
    zulip_ready = asyncio.Event()

    async def forward_discord_to_zulip(message: discord.Message) -> None:
        await discord_ready.wait()
        await zulip_ready.wait()
        content = _format_discord_to_zulip(settings, message)
        await zulip.send_message(settings.zulip_stream, settings.zulip_topic, content)

    async def forward_zulip_to_discord(message: ZulipMessage) -> None:
        await discord_ready.wait()
        await zulip_ready.wait()
        channel = discord_client.get_channel(settings.discord_channel_id)
        if channel is None:
            channel = await discord_client.fetch_channel(settings.discord_channel_id)
        if not isinstance(channel, discord.TextChannel):
            raise RuntimeError("Configured Discord channel is not a text channel")
        await channel.send(
            _format_zulip_to_discord(settings, message),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    intents = discord.Intents.default()
    intents.message_content = True
    discord_client = DiscordBridgeClient(
        channel_id=settings.discord_text_channel_id,
        on_bridge_message=forward_discord_to_zulip,
        intents=intents,
    )
    original_on_ready = discord_client.on_ready

    async def wrapped_on_ready() -> None:
        await original_on_ready()
        discord_ready.set()

    discord_client.on_ready = wrapped_on_ready  # type: ignore[assignment]

    async def zulip_loop() -> None:
        try:
            await zulip.run_event_loop(
                settings.zulip_stream,
                settings.zulip_topic,
                forward_zulip_to_discord,
                ready_event=zulip_ready,
            )
        finally:
            await zulip.aclose()

    discord_task = asyncio.create_task(discord_client.start(settings.discord_token))
    zulip_task = asyncio.create_task(zulip_loop())

    try:
        done, pending = await asyncio.wait(
            {discord_task, zulip_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            task.result()
    finally:
        for task in (discord_task, zulip_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(discord_task, zulip_task, return_exceptions=True)
        await discord_client.close()


def main() -> None:
    asyncio.run(run())
