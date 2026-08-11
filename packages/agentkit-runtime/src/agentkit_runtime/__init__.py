"""agentkit-runtime: M2 ``Orchestrator`` Protocol implementation (langgraph StateGraph).

LanggraphOrchestrator holds a langchain ``BaseChatModel`` + a ``ComponentAdapter``,
drives the Option B core loop (backend-sync verbs) and yields ``CopilotFunctionCall``
for frontend verbs. Provider-neutral: ``langchain-openai`` / ``langchain-anthropic`` /
``langchain-ollama`` are the caller's concern (§6.4). See ``docs/contracts.md`` for
the frozen seam this implements.
"""

from __future__ import annotations

from agentkit_runtime.messages import to_langchain_messages
from agentkit_runtime.orchestrator import LanggraphOrchestrator
from agentkit_runtime.tools import FrontendActionRequested


__all__ = [
    "FrontendActionRequested",
    "LanggraphOrchestrator",
    "to_langchain_messages",
]
