from pydantic import BaseModel
from clovers_client import Config as BaseConfig


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


class Config(BaseConfig):
    user_profile: UserProfileConfig = UserProfileConfig()
    memory: MemoryConfig = MemoryConfig()
