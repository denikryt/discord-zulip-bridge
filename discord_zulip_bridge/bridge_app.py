from __future__ import annotations

import asyncio

import discord

from .bridge_config import Settings
from .bridge_discord import DiscordBridgeClient
from .bridge_storage import BridgeStore
from .bridge_zulip import ZulipBridge, ZulipMessage


def _format_discord_to_zulip(settings: Settings, message: discord.Message) -> str:
    parts: list[str] = []
    guild_name = message.guild.name if message.guild is not None else "Unknown guild"
    parts.append(f"➤ *{guild_name}*")
    parts.append(f"**{message.author.display_name}**")
    parts.append(message.content or "_No text content_")
    if message.attachments:
        parts.append("")
        parts.append("Attachments:")
        for attachment in message.attachments:
            parts.append(f"- {attachment.url}")
    return "\n".join(parts)


def _format_zulip_to_discord(settings: Settings, message: ZulipMessage) -> str:
    parts: list[str] = []
    parts.append(f"**{message.sender_full_name}**")
    parts.append(message.content or "_No text content_")
    return "\n".join(parts)


def _forum_topic_for_thread(thread: discord.Thread) -> str:
    base = thread.name.strip() or "discord-thread"
    if len(base) <= 80:
        return base
    return base[:80].rstrip()


def _discord_thread_name(topic: str) -> str:
    clean = topic.strip() or "zulip-topic"
    if len(clean) <= 100:
        return clean
    return clean[:97].rstrip() + "..."


async def run() -> None:
    print("[bridge] starting")
    settings = Settings.load()
    print(
        "[bridge] config loaded "
        f"text_channel={settings.discord_text_channel_id} "
        f"forum_channel={settings.discord_forum_channel_id} "
        f"text_stream={settings.zulip_text_stream!r} "
        f"text_topic={settings.zulip_text_topic!r} "
        f"forum_stream={settings.zulip_forum_stream!r}"
    )
    store = BridgeStore(settings.bridge_db_path)
    print(f"[bridge] sqlite db={settings.bridge_db_path!r}")
    zulip = ZulipBridge(
        site=settings.zulip_site,
        bot_email=settings.zulip_bot_email,
        api_key=settings.zulip_api_key,
    )

    discord_ready = asyncio.Event()
    zulip_ready = asyncio.Event()

    async def forward_discord_text_to_zulip(message: discord.Message) -> None:
        await discord_ready.wait()
        await zulip_ready.wait()
        print(f"[bridge] discord text -> zulip message_id={message.id} channel={message.channel.id}")
        await zulip.send_message(
            settings.zulip_text_stream,
            settings.zulip_text_topic,
            _format_discord_to_zulip(settings, message),
        )

    async def forward_discord_forum_to_zulip(message: discord.Message) -> None:
        await discord_ready.wait()
        await zulip_ready.wait()
        if not isinstance(message.channel, discord.Thread):
            return
        print(f"[bridge] discord forum -> zulip thread_id={message.channel.id} thread_name={message.channel.name!r}")
        topic = await asyncio.to_thread(store.get_topic_for_thread, message.channel.id)
        if topic is None:
            topic = _forum_topic_for_thread(message.channel)
            print(f"[bridge] create forum mapping thread_id={message.channel.id} topic={topic!r}")
            await asyncio.to_thread(store.store_forum_mapping, message.channel.id, message.channel.name, topic)
        else:
            print(f"[bridge] reuse forum mapping thread_id={message.channel.id} topic={topic!r}")
        await zulip.send_message(
            settings.zulip_forum_stream,
            topic,
            _format_discord_to_zulip(settings, message),
        )

    async def forward_zulip_message_to_discord(message: ZulipMessage) -> None:
        await discord_ready.wait()
        await zulip_ready.wait()
        print(f"[bridge] zulip -> discord stream={message.stream!r} topic={message.topic!r} message_id={message.message_id}")

        if message.stream == settings.zulip_text_stream and message.topic == settings.zulip_text_topic:
            channel = discord_client.get_channel(settings.discord_text_channel_id)
            if channel is None:
                channel = await discord_client.fetch_channel(settings.discord_text_channel_id)
            if not isinstance(channel, discord.TextChannel):
                raise RuntimeError("Configured Discord text channel is not a text channel")
            print(f"[bridge] sending to discord text channel={channel.id}")
            await channel.send(
                _format_zulip_to_discord(settings, message),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        if message.stream != settings.zulip_forum_stream:
            print("[bridge] ignore zulip message for unrelated stream")
            return

        mapping = await asyncio.to_thread(store.get_thread_for_topic, message.topic)
        content = _format_zulip_to_discord(settings, message)
        if mapping is None:
            print(f"[bridge] no forum mapping for topic={message.topic!r}, creating thread")
            forum_channel = discord_client.get_channel(settings.discord_forum_channel_id)
            if forum_channel is None:
                forum_channel = await discord_client.fetch_channel(settings.discord_forum_channel_id)
            if not isinstance(forum_channel, discord.ForumChannel):
                raise RuntimeError("Configured Discord forum channel is not a forum channel")
            created = await forum_channel.create_thread(
                name=_discord_thread_name(message.topic),
                content=content,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            thread = getattr(created, "thread", None)
            if thread is None and isinstance(created, tuple):
                thread = next((item for item in created if isinstance(item, discord.Thread)), None)
            if thread is None and isinstance(created, discord.Thread):
                thread = created
            if isinstance(thread, discord.Thread):
                print(f"[bridge] created discord thread id={thread.id} name={thread.name!r}")
                await asyncio.to_thread(store.store_forum_mapping, thread.id, thread.name, message.topic)
            return

        thread_id, _thread_name = mapping
        print(f"[bridge] forum mapping hit topic={message.topic!r} thread_id={thread_id}")
        thread = discord_client.get_channel(thread_id)
        if thread is None:
            thread = await discord_client.fetch_channel(thread_id)
        if not isinstance(thread, discord.Thread):
            raise RuntimeError("Mapped Discord forum thread is missing or invalid")
        print(f"[bridge] sending to discord thread id={thread.id}")
        await thread.send(content, allowed_mentions=discord.AllowedMentions.none())

    intents = discord.Intents.default()
    intents.message_content = True
    discord_client = DiscordBridgeClient(
        text_channel_id=settings.discord_text_channel_id,
        forum_channel_id=settings.discord_forum_channel_id,
        on_text_message=forward_discord_text_to_zulip,
        on_forum_message=forward_discord_forum_to_zulip,
        ready_event=discord_ready,
        intents=intents,
    )

    async def zulip_loop() -> None:
        try:
            print("[bridge] starting zulip loop")
            await zulip.run_event_loop(
                [settings.zulip_text_stream, settings.zulip_forum_stream],
                forward_zulip_message_to_discord,
                ready_event=zulip_ready,
            )
        finally:
            print("[bridge] closing zulip client")
            await zulip.aclose()

    print("[bridge] starting discord client task")
    discord_task = asyncio.create_task(discord_client.start(settings.discord_token))
    print("[bridge] starting zulip task")
    zulip_task = asyncio.create_task(zulip_loop())

    try:
        done, pending = await asyncio.wait({discord_task, zulip_task}, return_when=asyncio.FIRST_COMPLETED)
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
