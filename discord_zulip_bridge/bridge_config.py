from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _require(*names: str) -> str:
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    raise RuntimeError(f"Missing required environment variable: {', '.join(names)}")


def _optional(default: str, *names: str) -> str:
    for name in names:
        value = _env(name)
        if value is not None:
            return value
    return default


def _parse_int(*names: str) -> int:
    raw = _require(*names)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {', '.join(names)} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    discord_token: str
    discord_text_channel_id: int
    discord_forum_channel_id: int
    zulip_site: str
    zulip_bot_email: str
    zulip_api_key: str
    zulip_text_stream: str
    zulip_text_topic: str
    zulip_forum_stream: str
    bridge_db_path: str
    discord_activity_prefix: str
    zulip_activity_prefix: str

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        return cls(
            discord_token=_require("DISCORD_TOKEN"),
            discord_text_channel_id=_parse_int("DISCORD_TEXT_CHANNEL", "discord_text_channel", "dicord_text_channel"),
            discord_forum_channel_id=_parse_int("DISCORD_FORUM_CHANNEL", "discord_forum_channel"),
            zulip_site=_require("ZULIP_SITE").rstrip("/"),
            zulip_bot_email=_require("ZULIP_BOT_EMAIL"),
            zulip_api_key=_require("ZULIP_API_KEY"),
            zulip_text_stream=_require("ZULIP_TEXT_STREAM", "zulip_text_stream"),
            zulip_text_topic=_require("ZULIP_TEXT_TOPIC", "zulip_text_topic"),
            zulip_forum_stream=_require("ZULIP_FORUM_STREAM", "zulip_forum_stream"),
            bridge_db_path=_optional(".bridge.sqlite3", "BRIDGE_DB_PATH"),
            discord_activity_prefix=_optional("[Discord]", "DISCORD_ACTIVITY_PREFIX"),
            zulip_activity_prefix=_optional("[Zulip]", "ZULIP_ACTIVITY_PREFIX"),
        )
