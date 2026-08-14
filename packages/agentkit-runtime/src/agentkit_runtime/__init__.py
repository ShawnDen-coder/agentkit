"""agentkit-runtime: ``Orchestrator`` Protocol implementation (langchain create_agent).

LanggraphOrchestrator holds a langchain ``BaseChatModel`` + a ``ComponentAdapter``,
drives the Option B core loop (backend-sync verbs) via ``create_agent`` and uses
langgraph's native ``interrupt()`` for frontend verbs (0.3.0 — no
``FrontendActionRequested`` exception). Provider-neutral: ``langchain-openai`` /
``langchain-anthropic`` / ``langchain-ollama`` are the caller's concern (§6.4).
See ``docs/contracts.md`` for the frozen seam this implements.
"""

from __future__ import annotations

from agentkit_runtime.adapter_tools import build_adapter_tools
from agentkit_runtime.frontend_tools import build_frontend_tools
from agentkit_runtime.messages import to_langchain_messages
from agentkit_runtime.orchestrator import LanggraphOrchestrator


__all__ = [
    "LanggraphOrchestrator",
    "build_adapter_tools",
    "build_frontend_tools",
    "to_langchain_messages",
]
