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

histories_config = CONFIG.histories
KEYWORD_FUZZ_THRESHOLD = histories_config.keyword_fuzz_threshold
RECALL_LIMIT = histories_config.recall_limit


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
        extra[KEY_HISTORY_INDEX] = index
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


async def intro_retrieve_history(agent: CloversAgent, session: Session):
    history_index = prepare_history_index(agent, session)
    message = "\n".join(format_message(t, c) for t, c, _ in session.message_history)
    lst = await asyncio.to_thread(history_index.search, message)
    if not lst:
        return ""
    top = heapq.nlargest(RECALL_LIMIT, lst, key=lambda x: x[0])
    entries = session.extra[KEY_HISTORY_ENTRIES] = cast(list[IndexedHistory], [])
    avg_score = sum(score for score, _ in top) / len(top)
    for score, meta in top:
        if score < avg_score:
            break
        entries.append(meta)
    memories = ["# 相关历史记录\n"]
    memories.extend(format_entry(*x) for x in enumerate(entries, start=1))
    return "\n".join(memories)


@TOOLS.register(
    "expand_history",
    "展开某条相关历史记录的完整内容",
    {"index": {"type": "integer", "description": "相关历史记录条目序号"}},
    category=ON_CHAT,
)
async def _(
    agent: CloversAgent,
    turn: Turn,
    event: Event,
    index: int,
):
    if not isinstance(index, int) or index <= 0:
        return f"Invalid index: {index}"
    try:
        entry = cast(IndexedHistory, turn.extra[KEY_HISTORY_ENTRIES][index - 1])
    except (KeyError, IndexError):
        return "Related history not found."
    return entry.content
