import heapq
import json
import base64
import random
import hashlib
from pathlib import Path
from clovers import Result
from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.api import OpenAIAPI
from clovers_agent.session import InputTag
from clovers_agent.embedding import batch_similarity
from clovers_agent.utils import load_jsonl, save_jsonl
from clovers_agent.config import CONFIG as AGENT_CONFIG
from clovers_agent.constants import ON_CHAT
from .constants import KEY_STICKER_PACK, SEND_STICKER_PROMPT
from ..base import TOOLS, CONFIG
from typing import cast

chat_config = CONFIG.chat
MAX_STICKER_CANDIDATES = chat_config.max_sticker_candidates
STIKER_PACK = Path(AGENT_CONFIG.path) / "StickerPack"
STIKER_PACK_METADATA = Path(STIKER_PACK) / "metadata.jsonl"


@TOOLS.register(
    "save_sticker",
    "将用户发送的图片保存到自己的贴纸收藏。",
    {
        "image_index": {
            "type": "integer",
            "description": "要保存的图片序号，从 0 开始，按照图片在当前用户消息中的出现顺序计算。支持负数索引，例如 -1 表示最后一张图片。",
        },
        "description": {
            "type": "string",
            "description": "结合使用场景、画面中的文字、角色、表情、情绪和表达含义对图片进行一句话简单描述。",
        },
    },
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, image_index: int, description: str):
    extra = turn.extra
    if KEY_STICKER_PACK not in extra:
        data = cast(list[list[str]], load_jsonl(STIKER_PACK_METADATA) or [])
        stickers = extra[KEY_STICKER_PACK] = [(name, desc) for name, desc in data]
    else:
        stickers = cast(list[tuple[str, str]], extra[KEY_STICKER_PACK])
    message = next((x for x in reversed(turn.payload["messages"]) if x["role"] == "user"), None)
    if not message or not (isinstance(content := message["content"], list)):
        return "未从当前用户信息中找到图片。"
    images = [x["image_url"]["url"] for x in content if x["type"] == "image_url"]
    try:
        url = images[image_index]
    except IndexError:
        return "当前用户消息中不存在指定序号的图片。"
    data_url = await agent._api.download_url(url)
    if not data_url:
        return "下载图片失败"
    name = next((f for f, d in stickers if d == description), None)
    if name:
        file = STIKER_PACK / name
    else:
        name = f"{hashlib.md5(data_url.encode()).hexdigest().upper()}.b64"
        file = STIKER_PACK / name
        sticker = (name, description)
        save_jsonl(STIKER_PACK_METADATA, sticker)
        stickers.append(sticker)
    file.write_text(data_url)
    return "保存成功"


@TOOLS.register(
    "send_sticker",
    "发送一张贴纸回应当前对话。发送后立即结束当前对话。",
    {
        "intent": {
            "type": "string",
            "description": "描述你对贴纸内容、情绪氛围或表达效果的期待，例如希望贴纸呈现的画面、传递的情绪或表达的态度。",
        }
    },
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, intent: str):
    extra = turn.extra
    if KEY_STICKER_PACK not in extra:
        data = cast(list[list[str]], load_jsonl(STIKER_PACK_METADATA) or [])
        stickers = extra[KEY_STICKER_PACK] = [(name, desc) for name, desc in data]
    else:
        stickers = cast(list[tuple[str, str]], extra[KEY_STICKER_PACK])
    if not stickers:
        return "没有可用的贴纸。"
    turn.create_turn()
    if len(stickers) > MAX_STICKER_CANDIDATES:
        similarities = batch_similarity([x for _, x in stickers], intent, agent.sentence_model)
        lst = heapq.nlargest(MAX_STICKER_CANDIDATES, zip(similarities, stickers), key=lambda x: x[0])
        stickers = [sticker for _, sticker in lst]
    prompt = SEND_STICKER_PROMPT.format("\n".join(f"{i}. {desc}" for i, desc in enumerate(stickers, start=1)))
    turn.create_payload(agent.api("router"), prompt)
    turn.input_text(intent)
    turn.payload["response_format"] = {"type": "json_object"}
    message = await turn.call_api()
    sticker_id = cast(int, random.choice(json.loads(message["content"])))
    name, desc = stickers[sticker_id]
    file = STIKER_PACK / name
    await event.send("image", file.read_text())
    session = agent.current_session(turn.session_id)
    session.record_history(InputTag.ASSISTANT, f"发送了贴纸 [{desc}]", session.last_active_time)
    session.complete_session()


if chat_config.mimo_tts.api_key:

    @TOOLS.on_startup
    async def _(agent: CloversAgent):
        global MIMO_TTS_API
        MIMO_TTS_API = OpenAIAPI(agent.async_client, chat_config.mimo_tts)

    @TOOLS.register(
        "send_voice",
        "发送一条语音消息",
        {
            "style": {"type": "string", "description": "语音语气、情绪、语速和语调等，描述这段话以什么样的表达风格说出来。"},
            "content": {"type": "string", "description": "语音中实际要说出的完整文本。"},
        },
        category=ON_CHAT,
    )
    async def _(agent: CloversAgent, turn: Turn, event: Event, style: str, content: str):
        payload = MIMO_TTS_API.build_payload()
        payload["messages"].append({"role": "user", "content": style})
        payload["messages"].append({"role": "assistant", "content": content})
        message = await MIMO_TTS_API.call_api(payload, turn.usage_counter)
        audio_data = cast(str, message["audio"]["data"])  # type: ignore
        audio_bytes = base64.b64decode(audio_data, validate=True)
        if not audio_bytes:
            return "语音生成失败：返回的音频为空。"
        await event.send("voice", audio_bytes)
        return "OK"


@TOOLS.register(
    "send_direct_message",
    "向用户发送一条私聊消息",
    {"message": {"type": "string", "description": "消息内容"}},
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, message: str):
    target = agent.current_session(f"private-{event.user_id}")
    timestamp = agent.current_session(turn.session_id).last_active_time
    async with target.execute_lock, target.aside_lock:
        await event.send("private_message", {"user_id": event.user_id, "data": Result("text", message)})
        target.record_history(event.nickname, event.message, timestamp)
        target.record_history(InputTag.ASSISTANT, message, timestamp)
    return "OK"


@TOOLS.register(
    "send_group_message",
    "向指定群发送一条群消息",
    {
        "group_id": {"type": "string", "description": "群ID"},
        "message": {"type": "string", "description": "消息内容"},
    },
    category=ON_CHAT,
)
async def _(agent: CloversAgent, turn: Turn, event: Event, group_id: str, message: str):
    target = agent.current_session(group_id)
    timestamp = agent.current_session(turn.session_id).last_active_time
    async with target.execute_lock, target.aside_lock:
        await event.send("group_message", {"group_id": group_id, "data": Result("text", message)})
        target.record_history(event.nickname, event.message, timestamp)
        target.record_history(InputTag.ASSISTANT, message, timestamp)
    return "OK"
