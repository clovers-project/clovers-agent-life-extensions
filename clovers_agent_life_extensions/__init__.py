from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.constants import ON_CHAT
from .base import TOOLS
from .user_profile import intro_user_profile
from .memory import intro_retrieve_memories


@TOOLS.on_intro(ON_CHAT)
async def _(agent: CloversAgent, turn: Turn, event: Event):
    session = agent.current_session(turn.session_id)
    unit = [
        await intro_retrieve_memories(agent, session),
        intro_user_profile(session, event),
    ]
    return "\n".join(unit)


__version__ = "0.3.0"
__all__ = ["TOOLS"]
