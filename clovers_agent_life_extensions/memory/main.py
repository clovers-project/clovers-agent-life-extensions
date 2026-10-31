import heapq
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.session import InputTag, Session
from clovers_agent.constants import ON_CHAT
from ..base import TOOLS, CONFIG
from .utils import HistoryEntry, IndexedHistory, HistoryIndex
from .constant import KEY_HISTORY_INDEX, KEY_HISTORY_ENTRIES

from typing import cast

memory = CONFIG.memory
KEYWORD_FUZZ_THRESHOLD = memory.keyword_fuzz_threshold


def prepare_history_index(agent: CloversAgent, session: Session) -> HistoryIndex:
    processed_dir = session.session_dir / "histories_processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    unrecognized_dir = session.session_dir / "histories_unrecognized"
    unrecognized_dir.mkdir(parents=True, exist_ok=True)
    extra = session.extra
    if KEY_HISTORY_INDEX in extra:
        index = cast(HistoryIndex, extra[KEY_HISTORY_INDEX])
    else:
        entries = []
        for path in tuple(processed_dir.iterdir()):
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
                new_file = shutil.move(path, processed_dir)
                history.path = Path(new_file)
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


def format_entry(i: int, entry: HistoryEntry):
    dt = datetime.fromtimestamp(entry.timestamp).strftime("%m-%d %H:%M")
    return f"{i}. {dt} {entry.overview}"


async def intro_retrieve_memories(agent: CloversAgent, session: Session, limit: int = 20):
    history_index = prepare_history_index(agent, session)
    message = "\n".join(format_message(t, c) for t, c, _ in session.message_history)
    lst = await asyncio.to_thread(history_index.search, message)
    if not lst:
        return ""
    top = heapq.nlargest(limit, lst, key=lambda x: x[0])
    entries = session.extra[KEY_HISTORY_ENTRIES] = cast(list[IndexedHistory], [])
    avg_score = sum(score for score, _ in top) / len(top)
    for score, meta in top:
        if score < avg_score:
            break
        entries.append(meta)
    memories = ["# 相关历史记忆\n"]
    memories.extend(format_entry(*x) for x in enumerate(entries, start=1))
    return "\n".join(memories)


@TOOLS.register(
    "expand_memory",
    "展开某条相关历史记忆的完整内容",
    {"memory_id": {"type": "integer", "description": "相关历史记忆条目序号"}},
    category=ON_CHAT,
)
async def _(
    agent: CloversAgent,
    turn: Turn,
    event: Event,
    memory_id: int,
):
    if not isinstance(memory_id, int) or memory_id <= 0:
        return f"Invalid memory_id: {memory_id}"
    try:
        entry = cast(IndexedHistory, turn.extra[KEY_HISTORY_ENTRIES][memory_id - 1])
    except (KeyError, IndexError):
        return "Related memory not found."
    return entry.content
