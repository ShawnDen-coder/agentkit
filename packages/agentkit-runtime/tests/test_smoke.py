"""Tests for agentkit-runtime (no real LLM call).

0.3.0 stage 2+4: rewritten for the plugin-repositioned architecture.

Covers:
  * ``LanggraphOrchestrator`` structurally satisfies the ``Orchestrator`` Protocol.
  * ``build_adapter_tools`` builds 5 tools; ``build_frontend_tools`` builds 4.
  * End-to-end: a scripted fake model emitting a frontend-verb tool_call makes
    ``run()`` yield a ``CopilotFunctionCall`` (validates ``create_agent`` +
    ``astream_events`` + ``interrupt()`` → ``on_tool_error`` mapping).
  * End-to-end: multi-hop backend loop emits status events + suggestions.
  * End-to-end: recursion limit yields a graceful chunk.
  * system_prompt is baked into the graph.
"""

from __future__ import annotations

import copy
from typing import Any

import agentkit_runtime
from agentkit_runtime import LanggraphOrchestrator
from agentkit_runtime import build_adapter_tools
from agentkit_runtime import build_frontend_tools
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages import SystemMessage
from pydantic import Field

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import Message
from agentkit_protocol import Orchestrator
from agentkit_protocol import QueryRequest
from agentkit_protocol import SessionContext


class _StubAdapter:
    """Minimal ComponentAdapter for the protocol check + integration tests (no real data)."""

    origin = "test"
    capabilities = AdapterCapabilities()

    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """Return empty catalog."""
        return []

    async def get_selection(self, ctx: SessionContext) -> ComponentData:
        """Return empty selection."""
        return ComponentData(kind="test.selection")

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Return a stub component."""
        return Component(component_id=component_id, origin="test", name="stub")

    async def get_component_data(self, ctx: SessionContext, component: Component, input_args: dict) -> ComponentData:
        """Return stub data."""
        return ComponentData(kind="test.data")

    async def refine_component(self, ctx: SessionContext, component: Component, refinement) -> ComponentData:
        """Return stub data."""
        return ComponentData(kind="test.data")

    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema:
        """Return stub schema."""
        return ComponentSchema(kind="test.schema")


class _FakeChatModel(FakeMessagesListChatModel):
    """FakeMessagesListChatModel that accepts ``bind_tools`` and returns fresh messages.

    ``create_agent`` calls ``model.bind_tools(tools)``; the base fake raises
    NotImplementedError. We ignore the tools (responses are pre-scripted with
    ``tool_calls``) and return self.

    The base fake returns the *same* stored ``AIMessage`` object on every cycle;
    langgraph mutates that message (run metadata / tool-call ids), so reusing it across
    iterations corrupts the graph state (manifests as ``KeyError: 'model'`` in routing).
    Real LLMs return a fresh message per call; we ``deepcopy`` on return to match that.

    ``recorded`` captures the message list passed to each ``_generate`` call (used to
    verify ``system_prompt`` is prepended by ``create_agent``).
    """

    recorded: list = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        """Ignore tools; return self (responses are pre-scripted)."""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # type: ignore[override]
        """Return a deepcopy of the cycled response (fresh object per invocation)."""
        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        result.generations[0].message = copy.deepcopy(result.generations[0].message)
        self.recorded.append(list(messages))
        return result


def _request(content: str = "test") -> QueryRequest:
    """Build a minimal QueryRequest with a human turn + a SessionContext."""
    return QueryRequest(
        messages=[Message(role="human", content=content)],
        session_context=SessionContext(user_identity="t", workspace_id="w", trace_id="x"),
    )


def test_orchestrator_satisfies_protocol() -> None:
    """LanggraphOrchestrator structurally satisfies the Orchestrator Protocol."""
    orch = LanggraphOrchestrator(_FakeChatModel(responses=[]), _StubAdapter())
    assert isinstance(orch, Orchestrator)


def test_imports() -> None:
    """Package exports the expected public symbols (0.3.0: no FrontendActionRequested)."""
    assert "LanggraphOrchestrator" in agentkit_runtime.__all__
    assert "build_adapter_tools" in agentkit_runtime.__all__
    assert "build_frontend_tools" in agentkit_runtime.__all__
    assert "to_langchain_messages" in agentkit_runtime.__all__
    assert "FrontendActionRequested" not in agentkit_runtime.__all__  # removed in 0.3.0


def test_adapter_tools_count_and_names() -> None:
    """build_adapter_tools returns 5 tools (7 backend verbs minus 2 stubs)."""
    tools = build_adapter_tools(_StubAdapter())
    assert len(tools) == 5
    assert {t.name for t in tools} == {
        "get_catalog",
        "get_component_data",
        "get_selection",
        "get_semantic_model",
        "refine_component",
    }


def test_frontend_tools_count_and_names() -> None:
    """build_frontend_tools returns 5 tools (4 frozen + 1 runtime extension)."""
    tools = build_frontend_tools()
    assert len(tools) == 5
    assert {t.name for t in tools} == {
        "add_component_to_dashboard",
        "update_component_in_dashboard",
        "manage_navigation_bar",
        "assign_tasks_to_agents",
        "connect_nodes",  # runtime extension (not in core's frozen 4)
    }


async def test_orchestrator_frontend_verb_yields_function_call() -> None:
    """A frontend-verb tool_call -> interrupt() -> run() yields CopilotFunctionCall."""
    model = _FakeChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "add_component_to_dashboard", "args": {"component_id": "x"}, "id": "c1"}],
            ),
        ],
    )
    orch = LanggraphOrchestrator(model, _StubAdapter(), max_hops=3)
    events = [e async for e in orch.run(_request("add it"))]
    fcs = [e for e in events if isinstance(e, CopilotFunctionCall)]
    assert len(fcs) == 1
    assert fcs[0].name == "add_component_to_dashboard"
    assert fcs[0].arguments == {"component_id": "x"}


async def test_orchestrator_multihop_backend_loop() -> None:
    """Multi-hop backend-sync loop (the Option B core path).

    Model calls get_catalog twice, then answers. run() emits a status per tool call and
    ends with suggestions.
    """
    gc = AIMessage(content="", tool_calls=[{"name": "get_catalog", "args": {}, "id": "c1"}])
    final = AIMessage(content="done")
    model = _FakeChatModel(responses=[gc, gc, final])
    orch = LanggraphOrchestrator(model, _StubAdapter(), max_hops=5)
    events = [e async for e in orch.run(_request("loop twice"))]
    # Two get_catalog calls -> two "running" status events with the catalog label.
    labels = [e.label for e in events if isinstance(e, CopilotStatusUpdate) and e.label]
    assert labels.count("正在获取目录") == 2
    # Stream completed normally -> no FunctionCall.
    assert not any(isinstance(e, CopilotFunctionCall) for e in events)


async def test_orchestrator_recursion_limit_graceful() -> None:
    """A model that never stops calling tools hits recursion_limit -> graceful chunk."""
    model = _FakeChatModel(
        responses=[AIMessage(content="", tool_calls=[{"name": "get_catalog", "args": {}, "id": "c1"}])],
    )
    orch = LanggraphOrchestrator(model, _StubAdapter(), max_hops=2)
    events = [e async for e in orch.run(_request("loop"))]
    chunks = [e for e in events if isinstance(e, CopilotMessageChunk)]
    assert any("已达调用上限" in c.text for c in chunks)


async def test_system_prompt_is_prepended_to_model_calls() -> None:
    """system_prompt is baked into the graph: create_agent prepends it as a SystemMessage."""
    model = _FakeChatModel(responses=[AIMessage(content="ok")])
    orch = LanggraphOrchestrator(
        model,
        _StubAdapter(),
        system_prompt="You are a BI copilot. Use the tools.",
    )
    [e async for e in orch.run(_request("hi"))]
    assert model.recorded, "model was not invoked"
    first = model.recorded[0][0]
    assert isinstance(first, SystemMessage)
    assert first.content == "You are a BI copilot. Use the tools."


async def test_no_system_prompt_means_no_prepended_system_message() -> None:
    """Without system_prompt, the model gets the raw message list (no synthetic SystemMessage)."""
    model = _FakeChatModel(responses=[AIMessage(content="ok")])
    orch = LanggraphOrchestrator(model, _StubAdapter())
    [e async for e in orch.run(_request("hi"))]
    assert model.recorded
    assert not any(isinstance(m, SystemMessage) for m in model.recorded[0])
