"""LanggraphOrchestrator: the M2 ``Orchestrator`` Protocol implementation.

Holds a langchain ``BaseChatModel`` + a ``ComponentAdapter``. ``run()`` is an async
generator that drives a ``create_agent`` (langchain v1) graph and maps its events onto
the 6 SSE events (Option B core loop, §6.1).

Stateless: state lives in ``request.messages``; no checkpointer. The frontend
``FunctionCall`` round-trip (``role=tool``) is the stateless equivalent of langgraph
``interrupt()`` - ``interrupt()`` requires a checkpointer, which would break the frozen
"all state in messages" contract (contracts.md). Frontend-verb tools raise
``FrontendActionRequested``; ``run()`` catches it, yields a ``CopilotFunctionCall``, and
ends the stream. On resume (``role=tool``) the orchestrator rebuilds langchain messages
from ``request.messages`` (synthesizing any missing ``AIMessage(tool_calls=[...])``) and
re-invokes the graph.

Streaming: ``astream_events(version="v2")`` + ``adispatch_custom_event`` (config-explicit,
3.10-safe). ``get_stream_writer`` / ``stream_mode="custom"`` is 3.11+-async-only and
cannot be used (the project supports Python 3.10).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.errors import GraphRecursionError

from agentkit_protocol import BaseSSE
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import QueryRequest
from agentkit_runtime.messages import to_langchain_messages
from agentkit_runtime.tools import FrontendActionRequested
from agentkit_runtime.tools import verb_tools


__all__ = ["LanggraphOrchestrator"]


# Canned follow-up suggestions (matches FakeOrchestrator for consistency).
# M3+: real suggestions come from a follow-up LLM call (extra latency + cost).
_CANNED_SUGGESTIONS: list[str] = [
    "再看一个组件",
    "按地区筛选",
    "解释一下这些数字",
]


async def _on_tool_error(exc: Exception, request: Any) -> str | None:
    """``ToolErrorMiddleware`` handler: NotImplementedError -> ToolMessage; else propagate.

    Returning a string converts the exception into an error ``ToolMessage`` (LLM retries);
    returning None re-raises (halts the run). FrontendActionRequested must propagate so
    ``run()`` can yield a ``CopilotFunctionCall``.
    """
    if isinstance(exc, NotImplementedError):
        return f"not implemented: {exc}"
    return None


class LanggraphOrchestrator:
    """LLM-backed orchestrator implementing the ``Orchestrator`` Protocol.

    Drives a ``create_agent`` graph (agent↔tools loop) with a ``recursion_limit`` budget.
    Backend-verb tools execute synchronously via the adapter and emit status/artifact
    side-channel events; frontend-verb tools raise ``FrontendActionRequested``, which
    ``run()`` catches to yield a ``CopilotFunctionCall`` and end the stream (Option B
    frontend round-trip).
    """

    def __init__(
        self,
        llm: BaseChatModel,
        adapter: ComponentAdapter,
        *,
        max_hops: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        """Compile the ``create_agent`` graph once (reused across requests).

        ``system_prompt`` is baked into the graph at construction (matching
        ``create_agent``'s ``system_prompt`` arg; a ``str`` is converted to a
        ``SystemMessage`` and prepended to the message list on every model call).
        For per-request customization, send a ``role=system`` ``Message`` - it is
        appended after the baked system prompt.

        ``recursion_limit`` is set per-request from ``max_hops``: each agent↔tools round
        is 2 super-steps (agent node + tools node), so ``max_hops * 2 + 2`` allows
        ``max_hops`` tool calls plus the final answering agent step.
        """
        self._max_hops = max_hops
        self._agent = create_agent(
            llm,
            tools=verb_tools(adapter),
            middleware=[ToolErrorMiddleware(aon_error=_on_tool_error)],
            system_prompt=system_prompt,
        )

    async def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine)."""
        yield CopilotStatusUpdate(status="thinking", label="思考中")
        messages = to_langchain_messages(request.messages)
        config = {
            "configurable": {"ctx": request.session_context},
            "recursion_limit": self._max_hops * 2 + 2,
        }
        try:
            async for ev in self._agent.astream_events(
                {"messages": messages},
                version="v2",
                config=config,
            ):
                sse = _map_event(ev)
                if sse is not None:
                    yield sse
        except FrontendActionRequested as fc:
            yield CopilotFunctionCall(name=fc.name, arguments=fc.arguments)
            return
        except GraphRecursionError:
            yield CopilotMessageChunk(text="已达调用上限。")
            return
        yield CopilotPromptSuggestions(suggestions=_CANNED_SUGGESTIONS)


def _map_event(ev: dict[str, Any]) -> BaseSSE | None:
    """Translate an ``astream_events`` (v2) event onto an SSE event (or None)."""
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
