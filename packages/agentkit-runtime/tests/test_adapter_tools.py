"""Tests for adapter_tools (0.3.0 stage 1): backend verbs as langchain tools.

Covers:
  * ``build_adapter_tools()`` builds 5 tools (one per implemented backend verb).
  * Tool names match the 5 backend verbs (excluding the 2 stubs
    ``get_skill_content`` / ``execute_tool``).
  * Invoking a tool calls the adapter method and emits a ``status`` side-channel
    event via ``adispatch_custom_event``.
  * The ``to_artifact`` profile hook, when provided, emits an ``artifact`` event.
  * Without the hook, no artifact event is emitted (runtime does NOT sniff shape).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
from agentkit_runtime.adapter_tools import build_adapter_tools
from langchain_core.runnables import RunnableConfig

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import SessionContext
from agentkit_protocol import TableArtifact


class StubAdapter:
    """ComponentAdapter stub for tests."""

    origin = "test"
    capabilities = AdapterCapabilities(supports_catalog=True, supports_selection=True)

    async def list_components(self, ctx):
        """Return empty catalog."""
        return []

    async def get_selection(self, ctx):
        """Return empty selection."""
        return ComponentData(kind="test.selection")

    async def get_component(self, ctx, component_id):
        """Return a stub component."""
        return Component(component_id=component_id, origin="test", name="stub")

    async def get_component_data(self, ctx, component, input_args):
        """Return stub tabular data."""
        return ComponentData(kind="test.data", columns=["a"], rows=[[1]])

    async def refine_component(self, ctx, component, refinement):
        """Return stub refined data."""
        return ComponentData(kind="test.refined")

    async def get_semantic_model(self, ctx, component):
        """Return stub schema."""
        return ComponentSchema(kind="test.schema")


def _ctx_config() -> tuple[Any, RunnableConfig]:
    """Build a SessionContext + matching RunnableConfig for tool invocation."""
    ctx = SessionContext(user_identity="t", workspace_id="w", trace_id="x")
    config: RunnableConfig = {"configurable": {"ctx": ctx}}
    return ctx, config


def test_adapter_tools_count_and_names() -> None:
    """build_adapter_tools returns 5 tools (7 backend verbs minus 2 stubs)."""
    tools = build_adapter_tools(StubAdapter())
    assert len(tools) == 5
    assert {t.name for t in tools} == {
        "get_catalog",
        "get_component_data",
        "get_selection",
        "get_semantic_model",
        "refine_component",
    }


def test_adapter_tools_stub_verbs_excluded() -> None:
    """get_skill_content / execute_tool are NOT exposed (NotImplementedError stubs)."""
    tools = build_adapter_tools(StubAdapter())
    names = {t.name for t in tools}
    assert "get_skill_content" not in names
    assert "execute_tool" not in names


@pytest.mark.asyncio
async def test_get_catalog_invokes_adapter_and_returns_json() -> None:
    """get_catalog tool calls adapter.list_components and returns JSON."""
    _, config = _ctx_config()
    tools = {t.name: t for t in build_adapter_tools(StubAdapter())}
    result = await tools["get_catalog"].ainvoke({}, config=config)
    parsed = json.loads(result)
    assert parsed == {"components": []}


@pytest.mark.asyncio
async def test_get_component_data_returns_json() -> None:
    """get_component_data tool returns the ComponentData dump as JSON."""
    _, config = _ctx_config()
    tools = {t.name: t for t in build_adapter_tools(StubAdapter())}
    result = await tools["get_component_data"].ainvoke({"component_id": "sales", "input_args": {}}, config=config)
    parsed = json.loads(result)
    assert parsed["kind"] == "test.data"


@pytest.mark.asyncio
async def test_to_artifact_hook_emits_artifact_event() -> None:
    """When to_artifact is provided and returns one, an artifact event is emitted."""
    captured_events: list = []

    async def _fake_dispatch(name: str, data: dict, config: RunnableConfig) -> None:
        captured_events.append((name, data))

    def to_table_artifact(data: dict) -> Any:
        if "columns" in data and "rows" in data:
            return TableArtifact(columns=list(data["columns"]), rows=[list(r) for r in data["rows"]])
        return None

    _, config = _ctx_config()
    with patch("agentkit_runtime.adapter_tools.adispatch_custom_event", _fake_dispatch):
        tools = {t.name: t for t in build_adapter_tools(StubAdapter(), to_artifact=to_table_artifact)}
        await tools["get_component_data"].ainvoke({"component_id": "x", "input_args": {}}, config=config)

    event_names = [name for name, _ in captured_events]
    assert "status" in event_names
    assert "artifact" in event_names


@pytest.mark.asyncio
async def test_no_to_artifact_hook_emits_no_artifact_event() -> None:
    """Without to_artifact, only status events are emitted (runtime does NOT sniff shape)."""
    captured_events: list = []

    async def _fake_dispatch(name: str, data: dict, config: RunnableConfig) -> None:
        captured_events.append((name, data))

    _, config = _ctx_config()
    with patch("agentkit_runtime.adapter_tools.adispatch_custom_event", _fake_dispatch):
        tools = {t.name: t for t in build_adapter_tools(StubAdapter())}  # no to_artifact
        await tools["get_component_data"].ainvoke({"component_id": "x", "input_args": {}}, config=config)

    event_names = [name for name, _ in captured_events]
    assert "status" in event_names
    assert "artifact" not in event_names  # no sniffing
