"""LanggraphOrchestrator: the ``Orchestrator`` Protocol implementation (0.3.0).

Holds a langchain ``BaseChatModel`` + a ``ComponentAdapter`` and compiles a
``create_agent`` graph once (reused across requests). ``run()`` is an async
generator mapping ``astream_events(version="v2")`` onto the 6 SSE events.

0.3.0 design (appendix E): langchain/langgraph plugin, not a parallel framework.
The orchestrator uses langgraph's native ``interrupt()`` for frontend-verb HITL
(no ``FrontendActionRequested`` exception). Stateful mode (checkpointer +
``thread_id``) is the default; the frontend resumes by re-POSTing with
``thread_id`` + ``resume``.

Non-obvious invariants a future change must preserve:

- **Frontend round-trip is ``interrupt()``, not a custom exception.** Frontend-verb
  tools call ``interrupt(args)`` which raises ``GraphInterrupt`` inside the tool.
  In ``astream_events(v2)`` this surfaces as ``on_tool_error`` with
  ``data["error"]`` being a ``GraphInterrupt`` instance whose ``.interrupts``
  tuple carries the ``Interrupt.value`` (the verb args). ``run()`` maps this to a
  ``CopilotFunctionCall`` SSE and ends the stream.
- **``ToolErrorMiddleware``** converts ``NotImplementedError`` (unimplemented
  backend-verb stubs) into an error ``ToolMessage`` for LLM recovery, and lets
  ``GraphInterrupt`` propagate (caught via ``on_tool_error``).
- **3.10 streaming constraint.** Side-channel ``status``/``artifact`` events are
  emitted with ``adispatch_custom_event`` (config-explicit, 3.10-safe) and
  consumed via ``astream_events(version="v2")`` ``on_custom_event``.
- **``recursion_limit`` = ``max_hops * 2 + 2``** (each agent↔tools round is 2
  super-steps: agent node + tools node, plus the final answering agent step).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ToolErrorMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import convert_to_messages
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphInterrupt
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from agentkit_protocol import BaseSSE
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import Principal
from agentkit_protocol import QueryRequest
from agentkit_runtime.adapter_tools import ToArtifact
from agentkit_runtime.adapter_tools import build_adapter_tools
from agentkit_runtime.frontend_tools import build_frontend_tools


__all__ = ["LanggraphOrchestrator"]


async def _on_tool_error(exc: Exception, request: Any) -> str | None:
    """``ToolErrorMiddleware`` handler: NotImplementedError -> ToolMessage; else propagate.

    Returning a string converts the exception into an error ``ToolMessage`` (LLM retries);
    returning None re-raises (halts the run). ``GraphInterrupt`` must propagate so
    ``run()`` can catch it via ``on_tool_error`` and yield a ``CopilotFunctionCall``.
    """
    if isinstance(exc, NotImplementedError):
        return f"not implemented: {exc}"
    return None


class LanggraphOrchestrator:
    """LLM-backed orchestrator implementing the ``Orchestrator`` Protocol (0.3.0).

    Drives a ``create_agent`` graph (agent↔tools loop) with a ``recursion_limit``
    budget. Backend-verb tools execute synchronously via the adapter and emit
    status/artifact side-channel events; frontend-verb tools call ``interrupt()``
    which ``run()`` catches and maps to a ``CopilotFunctionCall`` SSE.

    Args:
        llm: A langchain ``BaseChatModel`` (caller instantiates, e.g. ``ChatOpenAI(...)``).
        adapter: The ``ComponentAdapter`` whose methods back the backend-verb tools.
        checkpointer: A langgraph checkpointer for stateful mode. Defaults to
            ``InMemorySaver()`` (per-process, not persistent). For production use a
            real checkpointer (``PostgresSaver``, ``RedisSaver``, ...).
        extra_tools: Additional langchain tools (skills, MCP gateway tools, ...).
            These are appended to the adapter + frontend tools. This is the
            idiomatic extension point — pass ``@tool``-decorated functions directly.
        to_artifact: Optional profile hook that converts a ``ComponentData`` dump
            into an ``Artifact``. If None, no artifact events are emitted.
        max_hops: Maximum agent↔tools rounds before ``GraphRecursionError``.
        system_prompt: Baked into the graph (``create_agent`` ``system_prompt`` arg).
            For per-request customization, send a ``role=system`` ``Message``.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        adapter: ComponentAdapter,
        *,
        checkpointer: Any = None,
        extra_tools: list[BaseTool] | None = None,
        to_artifact: ToArtifact | None = None,
        authorizer: Any = None,
        principal_resolver: Any = None,
        max_hops: int = 5,
        system_prompt: str | None = None,
    ) -> None:
        """Compile the ``create_agent`` graph once (reused across requests).

        See class docstring for parameter descriptions.
        """
        self._max_hops = max_hops
        self._authorizer = authorizer
        self._principal_resolver = principal_resolver
        tools = [
            *build_adapter_tools(adapter, to_artifact=to_artifact, authorizer=authorizer),
            *build_frontend_tools(),
            *(extra_tools or []),
        ]
        self._agent = create_agent(
            llm,
            tools=tools,
            middleware=[ToolErrorMiddleware(aon_error=_on_tool_error)],
            checkpointer=checkpointer or InMemorySaver(),
            system_prompt=system_prompt,
        )

    async def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine).

        Stateful mode (``request.thread_id`` set): uses the checkpointer to
        resume an existing thread. If ``request.resume`` is set, sends
        ``Command(resume=...)`` to resume from a prior ``interrupt()``.

        Stateless mode (``request.thread_id`` None): generates a per-request
        thread_id; the checkpointer (default ``InMemorySaver``) holds state only
        within this request.
        """
        yield CopilotStatusUpdate(status="thinking", label="思考中")

        thread_id = request.thread_id or f"req-{id(request)}"
        # Resolve the Principal for per-verb authz (if an authorizer is configured).
        if self._authorizer is not None:
            if self._principal_resolver is not None:
                principal = self._principal_resolver(request)
            else:
                principal = Principal(
                    user_identity=request.session_context.user_identity,
                    user_permissions=tuple(request.session_context.user_permissions),
                    auth_token=request.session_context.auth_token,
                    workspace_id=request.session_context.workspace_id,
                )
        else:
            principal = None
        config: dict[str, Any] = {
            "configurable": {"thread_id": thread_id, "ctx": request.session_context},
            "recursion_limit": self._max_hops * 2 + 2,
        }
        if principal is not None:
            config["configurable"]["principal"] = principal

        if request.resume is not None:
            # Resume from a prior CopilotFunctionCall interrupt.
            input_payload: dict[str, Any] = {"resume": Command(resume=request.resume)}
        else:
            messages = convert_to_messages([m.model_dump() for m in request.messages])
            input_payload = {"messages": messages}

        try:
            events = self._agent.astream_events(input_payload, version="v2", config=config)
            try:
                async for ev in events:
                    sse = _map_event(ev)
                    if sse is not None:
                        yield sse
            finally:
                # Explicitly close the astream_events generator. When the consumer
                # (e.g. ChatPanel) returns early after a CopilotFunctionCall,
                # GeneratorExit is thrown into run() at the yield point. The
                # implicit async-for cleanup calls aclose() on astream_events, but
                # langgraph's generator doesn't handle GeneratorExit cleanly
                # (RuntimeError: async generator ignored GeneratorExit). We close
                # it ourselves and suppress the cleanup error.
                with contextlib.suppress(Exception):
                    await events.aclose()
        except GraphInterrupt:
            # Fallback if not caught via on_tool_error (defensive — normally
            # the interrupt surfaces as on_tool_error and _map_event handles it).
            return
        except GraphRecursionError:
            yield CopilotMessageChunk(text="已达调用上限。")
            return


def _map_event(ev: dict[str, Any]) -> BaseSSE | None:
    """Translate an ``astream_events`` (v2) event onto an SSE event (or None)."""
    kind = ev.get("event")

    if kind == "on_chat_model_stream":
        chunk = ev.get("data", {}).get("chunk")
        text = getattr(chunk, "content", "") if chunk is not None else ""
        if isinstance(text, str) and text:
            return CopilotMessageChunk(text=text)
        return None

    if kind == "on_tool_error":
        # interrupt() surfaces here: GraphInterrupt with .args[0] = list[Interrupt].
        err = ev.get("data", {}).get("error")
        if isinstance(err, GraphInterrupt) and err.args:
            interrupts = err.args[0] if isinstance(err.args[0], list) else list(err.args[0])
            if interrupts:
                interrupt_obj = interrupts[0]
                value = interrupt_obj.value
                # The interrupt value is the dict passed to interrupt(args) by the
                # frontend-verb tool. The verb name is the tool name from the event.
                tool_name = ev.get("name", "")
                return CopilotFunctionCall(
                    name=tool_name,
                    arguments=value if isinstance(value, dict) else {"value": value},
                    tool_call_id=interrupt_obj.id,  # langgraph interrupt id (string)
                )
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
