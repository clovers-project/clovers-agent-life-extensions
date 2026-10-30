import shutil
from pathlib import Path
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.session import InputTag, Session
from clovers_agent.constants import ON_CHAT
from ..base import TOOLS, CONFIG
from .utils import HistoryEntry, HistoryIndex
from .constant import KEY_HISTORY_INDEX

from typing import cast

memory = CONFIG.memory
KEYWORD_FUZZ_THRESHOLD = memory.keyword_fuzz_threshold


def prepare_history_index(agent: CloversAgent, session: Session) -> HistoryIndex:
    archive_dir = session.session_dir / "collected_histories"
    archive_dir.mkdir(parents=True, exist_ok=True)
    unrecognized_dir = session.session_dir / "unrecognized_histories"
    unrecognized_dir.mkdir(parents=True, exist_ok=True)
    extra = session.extra
    if KEY_HISTORY_INDEX in extra:
        index = cast(HistoryIndex, extra[KEY_HISTORY_INDEX])
    else:
        entries = []
        for path in tuple(archive_dir.iterdir()):
            history = HistoryEntry.from_file(path)
            if history is None:
                shutil.move(path, unrecognized_dir)
                continue
            entries.append(history)
        index = HistoryIndex(KEYWORD_FUZZ_THRESHOLD, entries, agent.sentence_model)
    hp_lst = list[tuple[HistoryEntry, Path]]()
    for path in tuple(session.history_dir.iterdir()):
        history = HistoryEntry.from_file(path)
        if history is None:
            shutil.move(path, unrecognized_dir)
            continue
        hp_lst.append((history, path))
    if hp_lst:
        max_t = max(history.timestamp for history, _ in hp_lst)
        for history, path in hp_lst:
            if history.timestamp < max_t:
                shutil.move(path, archive_dir)
                index.update(history)
    return index


def format_message(tag: InputTag | str, content: str):
    match tag:
        case InputTag.ASSISTANT:
            return content
        case str():
            return tag + " " + content
        case _:
            return ""


def retrieve_memories(agent: CloversAgent, turn: Turn):
    session = agent.current_session(turn.session_id)
    history_index = prepare_history_index(agent, session)
    message = "\n".join(format_message(t, c) for t, c, _ in session.message_history)
    lst = history_index.search(message)
    if not lst:
        return ""
    lst.sort(key=lambda x: x[0], reverse=True)
    for score, meta in lst[:5]:
        print(score, meta.overview)
    return ""


# @TOOLS.register(
#     "block_user",
#     "拉黑当前用户",
#     {"block_days": {"type": "number", "description": "拉黑天数，默认 7 天"}},
#     category=ON_CHAT,
# )
# async def _(agent: CloversAgent, turn: Turn, event: Event, block_days: int = 7):
#     user_id = event.user_id
#     user_profile_json = USER_PROFILE / f"{user_id}.json"
#     block_t = min(max(block_days, 1), 30) * 86400 + time.time()
#     if user_profile_json.exists():
#         user_profile = UserProfile.model_validate_json(user_profile_json.read_text(encoding="utf-8"))
#         user_profile.block_until = block_t
#     else:
#         user_profile = UserProfile(nickname=event.nickname, block_until=block_t)
#     user_profile_json.write_text(user_profile.model_dump_json(indent=4), encoding="utf-8")
#     return f"OK"
