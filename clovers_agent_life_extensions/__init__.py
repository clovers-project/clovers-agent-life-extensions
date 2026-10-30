from clovers_agent import CloversAgent, Turn, Event
from clovers_agent.constants import ON_CHAT
from .base import TOOLS
from .user_profile import intro_user_profile
from .memory import collect_memory


@TOOLS.on_intro(ON_CHAT)
async def _(agent: CloversAgent, turn: Turn, event: Event):
    unit = [
        collect_memory(agent, turn),
        intro_user_profile(turn, event),
    ]
    return "\n".join(unit)


__version__ = "0.3.0"
__all__ = ["TOOLS"]
