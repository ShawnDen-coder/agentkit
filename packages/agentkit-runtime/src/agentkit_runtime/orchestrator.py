"""LanggraphOrchestrator: the M2 ``Orchestrator`` Protocol implementation.

Holds a langchain ``BaseChatModel`` + a ``ComponentAdapter``. ``run()`` is an async
generator that drives the langgraph ``StateGraph`` and maps its events onto the 6 SSE
events (Option B core loop, §6.1).

Stateless: state lives in ``request.messages``; no checkpointer. On a frontend
``FunctionCall`` round-trip resume (``role=tool``), the orchestrator rebuilds the
langchain messages from ``request.messages`` (synthesizing any missing
``AIMessage(tool_calls=[...])``) and re-invokes the graph.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.language_models import BaseChatModel

from agentkit_protocol import BaseSSE
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import QueryRequest
from agentkit_runtime.graph import build_graph
from agentkit_runtime.messages import to_langchain_messages
from agentkit_runtime.tools import FrontendActionRequested
from agentkit_runtime.tools import build_tool_handlers
from agentkit_runtime.tools import verb_tool_schemas


__all__ = ["LanggraphOrchestrator"]


# Canned follow-up suggestions (matches FakeOrchestrator for consistency).
# M3+: real suggestions come from a follow-up LLM call (extra latency + cost).
_CANNED_SUGGESTIONS: list[str] = [
    "再看一个组件",
    "按地区筛选",
    "解释一下这些数字",
]


class LanggraphOrchestrator:
    """LLM-backed orchestrator implementing the ``Orchestrator`` Protocol.

    Drives a langgraph ``StateGraph`` (``agent`` ↔ ``tools``) with a ``MAX_HOPS`` budget.
    Backend-verb tool calls execute synchronously via the adapter; frontend-verb tool
    calls raise ``FrontendActionRequested``, which ``run()`` catches to yield a
    ``CopilotFunctionCall`` and end the stream (Option B frontend round-trip).
    """

    def __init__(
        self,
        llm: BaseChatModel,
        adapter: ComponentAdapter,
        *,
        max_hops: int = 5,
    ) -> None:
        """Bind tools to the LLM and compile the graph once (reused across requests)."""
        self._llm = llm
        self._adapter = adapter
        self._max_hops = max_hops
        self._bound = llm.bind_tools(verb_tool_schemas())
        self._handlers = build_tool_handlers(adapter)
        self._graph = build_graph(self._bound, self._handlers, adapter, max_hops)

    async def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine)."""
        yield CopilotStatusUpdate(status="thinking", label="思考中")
        messages = to_langchain_messages(request.messages)
        ctx = request.session_context
        try:
            async for ev in self._graph.astream_events(
                {"messages": messages, "hops": 0, "ctx": ctx},
                version="v2",
            ):
                sse = _map_event(ev)
                if sse is not None:
                    yield sse
        except FrontendActionRequested as fc:
            yield CopilotFunctionCall(name=fc.name, arguments=fc.arguments)
            return
        yield CopilotPromptSuggestions(suggestions=_CANNED_SUGGESTIONS)


def _map_event(ev: dict[str, Any]) -> BaseSSE | None:
    """Translate a langgraph ``astream_events`` event onto an SSE event (or None)."""
    kind = ev.get("event")
    if kind == "on_chat_model_stream":
        chunk = ev.get("data", {}).get("chunk")
        text = getattr(chunk, "content", "") if chunk is not None else ""
        # Skip empty deltas (tool-call chunks carry no text).
        if isinstance(text, str) and text:
            return CopilotMessageChunk(text=text)
        return None
    if kind == "on_custom_event":
        name = ev.get("name")
        data = ev.get("data", {})
        if name == "status":
            return CopilotStatusUpdate(
                status=data.get("status", "running"),
                label=data.get("label"),
            )
        if name == "artifact":
            artifact = data.get("artifact")
            if artifact is not None:
                return CopilotMessageArtifact(artifact=artifact)
        return None
    return None
