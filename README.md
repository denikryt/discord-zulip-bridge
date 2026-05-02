# discord-zulip-bridge

Bridge bot with two modes:

- Discord text channel -> one Zulip stream/topic
- Discord forum channel -> one Zulip stream with dynamic topics stored in SQLite

## Setup

1. Create a Discord bot.
2. Enable Discord **Message Content Intent**.
3. Create a Zulip **Generic bot**.
4. Subscribe the Zulip bot to the stream in `ZULIP_FORUM_CHANNEL`.
5. Copy `.env.example` to `.env` and fill the variables below.
6. Install and run the bot.

## `.env`

Required:

```env
DISCORD_TOKEN=...
DISCORD_TEXT_CHANNEL=...
DISCORD_FORUM_CHANNEL=...
ZULIP_SITE=...
ZULIP_BOT_EMAIL=...
ZULIP_API_KEY=...
ZULIP_TEXT_STREAM=...
ZULIP_TEXT_TOPIC=...
ZULIP_FORUM_STREAM=...
```

Optional:

```env
BRIDGE_DB_PATH=.bridge.sqlite3
DISCORD_ACTIVITY_PREFIX=[Discord]
ZULIP_ACTIVITY_PREFIX=[Zulip]
```

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
discord-zulip-bridge
```

## Behavior

- Messages from `DISCORD_TEXT_CHANNEL` go to `ZULIP_FORUM_CHANNEL` in topic `ZULIP_TEXT_TOPIC`.
- Messages from `DISCORD_TEXT_CHANNEL` go to `ZULIP_TEXT_STREAM` in topic `ZULIP_TEXT_TOPIC`.
- Messages from `DISCORD_FORUM_CHANNEL` threads go to `ZULIP_FORUM_STREAM` in a topic created from the Discord thread and stored in SQLite.
- Messages in `ZULIP_TEXT_STREAM` and topic `ZULIP_TEXT_TOPIC` go to the Discord text channel.
- Messages in other topics of `ZULIP_FORUM_STREAM` create or reuse Discord forum threads.
- New Zulip topics are created automatically by sending the first message to them.
