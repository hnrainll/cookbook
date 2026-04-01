"""Per-platform text limit helpers."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextLimit:
    platform: str
    reply_label: str
    default_limit: int


FANFOU_TEXT_LIMIT = TextLimit(
    platform="fanfou",
    reply_label="饭否",
    default_limit=140,
)

THREADS_TEXT_LIMIT = TextLimit(
    platform="threads",
    reply_label="Threads",
    default_limit=500,
)

BLUESKY_TEXT_LIMIT = TextLimit(
    platform="bluesky",
    reply_label="Bluesky",
    default_limit=300,
)

MASTODON_TEXT_LIMIT = TextLimit(
    platform="mastodon",
    reply_label="Mastodon",
    default_limit=500,
)


def text_too_long_reply(limit: TextLimit, max_characters: int | None = None) -> str:
    actual_limit = max_characters or limit.default_limit
    if actual_limit == limit.default_limit:
        return f"[{limit.reply_label}] 消息长度超过 {actual_limit} 字，无法发送"
    return f"[{limit.reply_label}] 消息长度超过当前实例 {actual_limit} 字限制，无法发送"


def caption_too_long_reply(limit: TextLimit, max_characters: int | None = None) -> str:
    actual_limit = max_characters or limit.default_limit
    if actual_limit == limit.default_limit:
        return f"[{limit.reply_label}] 图片说明超过 {actual_limit} 字，无法发送"
    return f"[{limit.reply_label}] 图片说明超过当前实例 {actual_limit} 字限制，无法发送"


def text_too_long_error(limit: TextLimit, max_characters: int | None = None) -> str:
    actual_limit = max_characters or limit.default_limit
    if actual_limit == limit.default_limit:
        return f"消息超过 {limit.reply_label} {actual_limit} 字限制"
    return f"消息超过 {limit.reply_label} 实例 {actual_limit} 字限制"


def caption_too_long_error(limit: TextLimit, max_characters: int | None = None) -> str:
    actual_limit = max_characters or limit.default_limit
    if actual_limit == limit.default_limit:
        return f"图片说明超过 {limit.reply_label} {actual_limit} 字限制"
    return f"图片说明超过 {limit.reply_label} 实例 {actual_limit} 字限制"
