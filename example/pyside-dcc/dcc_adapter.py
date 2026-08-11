"""Mock DCC ``ComponentAdapter`` for the PySide example (narrow waist ①).

A fake DCC host (Maya-like) with a scene of selectable nodes. DCC adapters are
selection-centric: ``get_selection`` returns the currently-selected scene nodes,
and ``get_component_data`` returns a node's attributes. Same ``ComponentAdapter``
contract as the BI adapter - this is the portability claim (narrow waist ① is
domain-neutral; BI vs DCC is just different envelope ``kind``s + profile fields).
"""

from __future__ import annotations

from typing import ClassVar

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext


class MockDccAdapter:
    """A fake DCC host scene: a cube, a light, and a camera."""

    origin = "mock-dcc"
    capabilities = AdapterCapabilities(
        supports_catalog=True,
        supports_selection=True,
        max_concurrent_fetch=1,
    )

    _SCENE: ClassVar[list[Component]] = [
        Component(
            component_id="cube1",
            origin="mock-dcc",
            name="立方体",
            schema=ComponentSchema(kind="dcc.node", type="mesh"),
        ),
        Component(
            component_id="light2",
            origin="mock-dcc",
            name="平行光",
            schema=ComponentSchema(kind="dcc.node", type="light"),
        ),
        Component(
            component_id="cam1",
            origin="mock-dcc",
            name="摄像机",
            schema=ComponentSchema(kind="dcc.node", type="camera"),
        ),
    ]

    _selected = "cube1"  # the "current selection" in the host tool

    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """Return the scene nodes (verb: get_catalog). RLS via ctx."""
        return [c.model_copy(deep=True) for c in self._SCENE]

    async def get_selection(self, ctx: SessionContext) -> ComponentData:
        """Return the currently-selected scene node (verb: get_selection)."""
        return ComponentData(kind="dcc.selection", nodes=[self._selected])

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Return a single scene node by id."""
        for c in self._SCENE:
            if c.component_id == component_id:
                return c.model_copy(deep=True)
        raise KeyError(component_id)

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, object]
    ) -> ComponentData:
        """Fetch a node's attributes (verb: get_component_data). RLS via ctx."""
        return ComponentData(
            kind="dcc.attributes",
            node=component.component_id,
            transform={"translate": [0, 0, 0], "rotate": [0, 0, 0], "scale": [1, 1, 1]},
            visible=True,
        )

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData:
        """Refine a node (verb: refine_component). Stubbed for the example."""
        return await self.get_component_data(ctx, component, {})

    async def get_semantic_model(
        self, ctx: SessionContext, component: Component
    ) -> ComponentSchema:
        """Fetch the node's schema (verb: get_semantic_model)."""
        return component.schema_
