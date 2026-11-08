from pydantic import BaseModel
from clovers_client import Config as BaseConfig
from clovers_agent.config import OpenAIConfig


class UserProfileConfig(BaseModel):
    profile_memory_size: int = 30
    """个人档案保留记忆条数"""
    reminder_cooldown_turns: int = 4
    """反向提示轮数（冷却期）：距上次档案更新不足该轮数时，不再触发提醒"""
    reminder_turns: int = 8
    """提醒个人档案更新对话轮数"""
    strong_reminder_turns: int = 16
    """强提醒个人档案更新对话轮数"""


class MemoryConfig(BaseModel):
    keyword_fuzz_threshold: float = 85
    """关键词模糊匹配阈值"""
    recall_limit: int = 30
    """记忆召回数量限制"""
    max_memory_size: int = 120
    """最大记忆条数"""


class ChatConfig(BaseModel):
    max_sticker_candidates: int = 32
    mimo_tts: OpenAIConfig = OpenAIConfig(
        url="https://api.xiaomimimo.com/v1",
        model="mimo-v2.5-tts",
        api_key="",
        extra_body={"format": "wav", "voice": "mimo_default"},
    )
    send_sticker_prompt: str = """\
你可以使用 `send_sticker` 工具发送贴纸，以贴纸代替文字回应当前对话。调用后，对话会立即结束。

- 当贴纸能够自然表达情绪、态度或回应时，优先考虑使用；无主题闲聊也可以用贴纸参与互动。
- 不要刻意寻找发送机会，不要连续或重复发送。
- 需要认真回答、提供信息或处理严肃话题时，优先使用文字。
- 如果上下文中尚无助手发送贴纸的记录，适度提高发送贴纸的优先级，但仍需结合对话场景判断。
"""


class Config(BaseConfig):
    user_profile: UserProfileConfig = UserProfileConfig()
    histories: MemoryConfig = MemoryConfig()
    chat: ChatConfig = ChatConfig()
