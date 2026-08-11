"""Smoke tests for agentkit-runtime (no real LLM call).

Verifies the LanggraphOrchestrator structurally satisfies the Orchestrator Protocol
and that the package imports cleanly. A real-LLM smoke test runs against the two
example apps (see the plan's smoke-test procedure).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import agentkit_runtime
from agentkit_runtime import LanggraphOrchestrator
from langchain_core.language_models import BaseChatModel

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import Orchestrator
from agentkit_protocol import SessionContext


class _StubAdapter:
    """Minimal ComponentAdapter for the protocol check (no real data)."""

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


def test_orchestrator_satisfies_protocol() -> None:
    """LanggraphOrchestrator(structurally) satisfies the Orchestrator Protocol."""
    stub_llm = MagicMock(spec=BaseChatModel)
    stub_llm.bind_tools.return_value = MagicMock()
    orch = LanggraphOrchestrator(stub_llm, _StubAdapter())
    assert isinstance(orch, Orchestrator)


def test_imports() -> None:
    """Package exports the expected public symbols."""
    assert "LanggraphOrchestrator" in agentkit_runtime.__all__
    assert "FrontendActionRequested" in agentkit_runtime.__all__
    assert "to_langchain_messages" in agentkit_runtime.__all__
