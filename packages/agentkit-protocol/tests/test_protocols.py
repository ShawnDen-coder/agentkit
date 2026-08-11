"""Contract tests for the ComponentAdapter Protocol (narrow waist ①)."""

from __future__ import annotations

from typing import Any

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext


def test_component_adapter_declares_get_selection() -> None:
    """get_selection is part of the ComponentAdapter contract (verb: get_selection)."""
    assert hasattr(ComponentAdapter, "get_selection")


class _CompleteAdapter:
    """Minimal adapter implementing every ComponentAdapter member."""

    origin = "test"
    capabilities = AdapterCapabilities()

    async def list_components(self, ctx: SessionContext) -> list[Component]: ...

    async def get_selection(self, ctx: SessionContext) -> ComponentData: ...

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component: ...

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, Any]
    ) -> ComponentData: ...

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData: ...

    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema: ...


class _AdapterMissingSelection:
    """Adapter lacking only get_selection -- must NOT satisfy the Protocol."""

    origin = "test"
    capabilities = AdapterCapabilities()

    async def list_components(self, ctx: SessionContext) -> list[Component]: ...

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component: ...

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, Any]
    ) -> ComponentData: ...

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData: ...

    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema: ...


def test_complete_adapter_satisfies_protocol() -> None:
    """An adapter implementing all members (incl. get_selection) is a ComponentAdapter."""
    assert isinstance(_CompleteAdapter(), ComponentAdapter)


def test_adapter_missing_selection_violates_protocol() -> None:
    """An adapter without get_selection is not a ComponentAdapter."""
    assert not isinstance(_AdapterMissingSelection(), ComponentAdapter)
