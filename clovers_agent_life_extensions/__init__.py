from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.constants import ON_CHAT
from .base import TOOLS, CONFIG
from .user_profile import intro_user_profile
from .memory import intro_retrieve_history
from . import chat_utils as chat_utils

LIFE_PROMPT = f"""

{CONFIG.chat.chat_utils_prompt}
"""


@TOOLS.on_startup
async def _(agent: CloversAgent):
    agent.chat_prompt = agent.chat_prompt + LIFE_PROMPT


@TOOLS.on_intro(ON_CHAT)
async def _(agent: CloversAgent, turn: Turn, event: Event):
    session = agent.current_session(turn.session_id)
    units = [
        await intro_retrieve_history(agent, session),
        intro_user_profile(session, event),
    ]
    return "\n---\n".join(filter(None, units))


__version__ = "0.3.4"
__all__ = ["TOOLS"]
