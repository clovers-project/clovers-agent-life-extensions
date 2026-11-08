import time
import contextlib
from pathlib import Path
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.session import Session
from clovers_agent.config import CONFIG as AGENT_CONFIG
from clovers_agent.constants import ON_CHAT, ROUTER_INTRO
from .constants import (
    KEY_USER_PROFILES,
    KEY_PROFILE_UPDATE_TURNS,
    UPDATE_USER_PROFILE,
    UPDATE_USER_PROFILE_PROMPT,
    EDIT_USER_PROFILE,
)
from ..base import TOOLS, CONFIG

from typing import cast
from .typing import UserProfile, MemoryItem, MemoryItemTuple

user_profile = CONFIG.user_profile
REMINDER_COOLDOWN_TURNS = user_profile.reminder_cooldown_turns
REMINDER_TURNS = user_profile.reminder_turns
STRONG_REMINDER_TURNS = user_profile.strong_reminder_turns
PROFILE_MEMORY_SIZE = user_profile.profile_memory_size

USER_PROFILE = Path(AGENT_CONFIG.path) / "UserProfile"


@TOOLS.on_intro(ROUTER_INTRO)
async def _(agent: CloversAgent, turn: Turn, event: Event):
    extra = turn.extra
    user_id = event.user_id
    if KEY_USER_PROFILES not in extra:
        user_profiles = extra[KEY_USER_PROFILES] = {}
    else:
        user_profiles = extra[KEY_USER_PROFILES]
    if user_id in user_profiles:
        return ""
    user_profile_file = USER_PROFILE / f"{user_id}.json"
    if not user_profile_file.exists():
        return ""
    try:
        data = user_profile_file.read_text(encoding="utf-8")
        user_profile = UserProfile.model_validate_json(data)
    except Exception:
        user_profile_file.unlink()
        return ""
    user_profiles[user_id] = user_profile
    if user_profile.block_until > time.time():
        agent.current_session(turn.session_id).complete_session()
    return ""


def intro_user_profile(session: Session, event: Event) -> str:
    extra = session.extra
    user_id = event.user_id
    user_profile = cast(dict[str, UserProfile], extra[KEY_USER_PROFILES]).get(event.user_id)
    if user_profile is None:
        return f"# 用户档案：{event.nickname}\n\n目前尚无该用户档案，请在**上下文足够充分**时进行使用 '{UPDATE_USER_PROFILE}' 工具进行第一次更新。"
    if KEY_PROFILE_UPDATE_TURNS not in extra:
        counter = extra[KEY_PROFILE_UPDATE_TURNS] = {}
    else:
        counter = extra[KEY_PROFILE_UPDATE_TURNS]
    count = counter[user_id] = counter.get(user_id, 0) + 1
    notes = [user_profile.to_markdown()]
    if count > STRONG_REMINDER_TURNS:
        notes.append(f"档案在 {count} 轮对话前更新。请及时使用 '{UPDATE_USER_PROFILE}' 工具对档案进行更新。")
    elif count > REMINDER_TURNS:
        notes.append(f"档案在 {count} 轮对话前更新。请确认用户档案是否过时。")
    elif count < REMINDER_COOLDOWN_TURNS:
        notes.append(f"档案在 {count} 轮对话前更新。除非用户提供了全新的长期重要信息，否则无需更新档案。")
    return "\n\n".join(notes)


@TOOLS.register(
    "block_user",
    "拉黑当前用户",
    {"block_days": {"type": "number", "description": "拉黑天数，默认 7 天"}},
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, block_days: int = 7):
    user_id = event.user_id
    user_profiles = cast(dict[str, UserProfile], turn.extra[KEY_USER_PROFILES])
    user_profile = user_profiles.get(event.user_id)
    block_t = min(max(block_days, 1), 30) * 86400 + time.time()
    if user_profile is None:
        user_profile = user_profiles[user_id] = UserProfile(nickname=event.nickname, block_until=block_t)
    else:
        user_profile.block_until = block_t
    USER_PROFILE.mkdir(parents=True, exist_ok=True)
    user_profile_file = USER_PROFILE / f"{user_id}.json"
    user_profile_file.write_text(user_profile.model_dump_json(indent=4), encoding="utf-8")
    return f"OK"


@TOOLS.register(
    UPDATE_USER_PROFILE,
    "用于更新助手对用户的印象档案。当用户约定称呼、展现偏好、或你对该用户的印象需要修正时，应主动调用此工具",
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, **kwargs):
    return UPDATE_USER_PROFILE_PROMPT


@TOOLS.register(
    EDIT_USER_PROFILE,
    f"在调用此工具前必须先调用`{UPDATE_USER_PROFILE}`",
    {
        "address_as": {"type": "string"},
        "tags": {"type": "string"},
        "preferences": {"type": "string"},
        "impression": {"type": "string"},
        "new_memories": {"type": "array", "items": {"type": "string"}},
        "promote_memories": {
            "type": "array",
            "items": {"type": "object", "properties": {"id": {"type": "integer"}, "content": {"type": "string"}}},
        },
        "demote_memory_ids": {"type": "array", "items": {"type": "integer"}},
    },
    category=ON_CHAT,
    required=[],
)
async def _(
    agent: CloversAgent,
    turn: Turn,
    event: Event,
    address_as: str = "",
    tags: str = "",
    preferences: str = "",
    impression: str = "",
    new_memories: list[str] | None = None,
    promote_memories: list[MemoryItem] | None = None,
    demote_memory_ids: list[int] | None = None,
):
    user_id = event.user_id
    user_profiles = cast(dict[str, UserProfile], turn.extra[KEY_USER_PROFILES])
    user_profile = user_profiles.get(event.user_id)
    if user_profile is None:
        user_profile = user_profiles[user_id] = UserProfile()
    user_profile.nickname = event.nickname
    if address_as:
        user_profile.address_as = address_as
    if tags:
        user_profile.tags = tags
    if preferences:
        user_profile.preferences = preferences
    if impression:
        user_profile.impression = impression
    old_memories: dict[int, MemoryItemTuple] = {int(x["id"]): (x["content"], x["star"]) for x in user_profile.memories}
    memories: list[MemoryItemTuple] = []
    if promote_memories:
        for x in promote_memories:
            if not "id" in x:
                if "content" in x:
                    memories.append((x["content"], 1))
                continue
            key = int(x["id"])
            c = x.get("content")
            if key not in old_memories:
                if c:
                    memories.append((c, 1))
            else:
                old_c, star = old_memories[key]
                memories.append((c or old_c, min(star + 1, 5)))
                del old_memories[key]
    if demote_memory_ids:
        for key in demote_memory_ids:
            if key not in old_memories:
                continue
            old_c, star = old_memories[key]
            memories.append((old_c, star - 1))
            del old_memories[key]
    if new_memories:
        memories.extend((x, 1) for x in new_memories)
    memories.extend(old_memories.values())
    if len(memories) >= PROFILE_MEMORY_SIZE:
        memories = sorted(((c, star - 1) for c, star in memories if star >= 1), key=lambda x: x[1], reverse=True)
    else:
        memories = sorted((x for x in memories if x[1] >= 0), key=lambda x: x[1], reverse=True)
    user_profile.memories.clear()
    user_profile.memories.extend({"id": i, "content": c, "star": star} for i, (c, star) in enumerate(memories, 1))
    USER_PROFILE.mkdir(parents=True, exist_ok=True)
    user_profile_file = USER_PROFILE / f"{user_id}.json"
    user_profile_file.write_text(user_profile.model_dump_json(indent=4), encoding="utf-8")
    with contextlib.suppress(KeyError):
        turn.extra[KEY_PROFILE_UPDATE_TURNS][user_id] = 0
    return "OK"
