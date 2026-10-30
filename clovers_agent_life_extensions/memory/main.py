import shutil
from pathlib import Path
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.session import InputTag, Session
from clovers_agent.constants import ON_CHAT
from ..base import TOOLS, CONFIG
from .utils import HistoryEntry, HistoryManager

memory = CONFIG.memory
KEYWORD_FUZZ_THRESHOLD = memory.keyword_fuzz_threshold


def collect_manager(agent: CloversAgent, session: Session) -> HistoryManager:
    collected_dir = session.session_dir / "collected_histories"
    collected_dir.mkdir(parents=True, exist_ok=True)
    unrecognized_dir = session.session_dir / "unrecognized_histories"
    unrecognized_dir.mkdir(parents=True, exist_ok=True)
    extra = session.extra
    if "history_manager" in extra:
        manager = extra["history_manager"]
    else:
        histories = []
        for file in tuple(file for file in collected_dir.iterdir()):
            history = HistoryEntry.from_file(file)
            if history is None:
                shutil.move(file, unrecognized_dir)
                continue
            histories.append(history)
        manager = HistoryManager(KEYWORD_FUZZ_THRESHOLD, histories)
    hp_lst = list[tuple[HistoryEntry, Path]]()
    for file in tuple(file for file in session.history_dir.iterdir()):
        history = HistoryEntry.from_file(file)
        if history is None:
            shutil.move(file, unrecognized_dir)
            continue
        hp_lst.append((history, file))
    if hp_lst:
        max_t = max(history.timestamp for history, _ in hp_lst)
        for history, file in hp_lst:
            if history.timestamp < max_t:
                shutil.move(file, collected_dir)
                manager.update(history)
    return manager


def format_input(tag: InputTag | str, content: str):
    match tag:
        case InputTag.ASSISTANT:
            return content
        case str():
            return tag + " " + content
        case _:
            return ""


def collect_memory(agent: CloversAgent, turn: Turn):
    session = agent.current_session(turn.session_id)
    manager = collect_manager(agent, session)
    message = "\n".join(format_input(t, c) for t, c, _ in session.message_history)
    lst = manager.search(message)
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
