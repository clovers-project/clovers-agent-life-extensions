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
        model="mimo-v2.5-tts-voiceclone",
        api_key="",
    )
    chat_utils_prompt: str = """\
部分发送工具提供的 stop_after_send 参数介绍：

- true（默认）：表示本次发送已经完成对用户的回复。消息发送成功后，立即结束当前对话执行。
- false：表示本次发送仅作为中间步骤。当发送后需要向用户补充回复或继续执行其他操作时，将此参数设置为 false

你可以使用 `send_sticker` 工具发送贴纸，以贴纸代替文字回应当前对话：

- 当贴纸能够自然地表达情绪、态度或回应时，优先考虑使用贴纸。对于没有明确主题的日常闲聊，也可以偶尔使用贴纸参与互动。
- 不要刻意寻找发送贴纸的机会，也不要连续或重复发送。如果不确定是否适合使用贴纸，优先选择文字回复。
- 如果当前上下文中还没有助手发送贴纸的记录，或者距离上次发送贴纸已经较久，可以适当提高使用贴纸的优先级，但仍需根据当前对话场景判断是否合适。
- 如果最近已经发送过贴纸，则适当降低再次发送贴纸的优先级，避免过于频繁地使用。
"""


class Config(BaseConfig):
    user_profile: UserProfileConfig = UserProfileConfig()
    histories: MemoryConfig = MemoryConfig()
    chat: ChatConfig = ChatConfig()
