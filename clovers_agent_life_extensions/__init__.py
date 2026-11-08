from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.constants import ON_CHAT
from .base import TOOLS
from .user_profile import intro_user_profile
from .memory import intro_retrieve_history
from .chat_utils import SEND_STIKER_PROMPT


@TOOLS.on_intro(ON_CHAT)
async def _(agent: CloversAgent, turn: Turn, event: Event):
    session = agent.current_session(turn.session_id)
    units = [
        await intro_retrieve_history(agent, session),
        intro_user_profile(session, event),
        SEND_STIKER_PROMPT,
    ]
    return "\n---\n".join(filter(None, units))


__version__ = "0.3.3"
__all__ = ["TOOLS"]
