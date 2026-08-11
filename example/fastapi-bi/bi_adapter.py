"""Mock BI ``ComponentAdapter`` for the FastAPI example (narrow waist ①).

A fake BI backend (Superset-like) with a small widget catalog and canned table
data. Demonstrates how a vendor implements ``ComponentAdapter``: this is the ONLY
contract a BI adapter implements. Core never reads the ``ComponentSchema`` /
``ComponentData`` content - they cross the protocol as opaque envelopes.
"""

from __future__ import annotations

from typing import ClassVar

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext


class MockBiAdapter:
    """A fake BI backend with two widgets and canned sales/revenue data."""

    origin = "mock-bi"
    capabilities = AdapterCapabilities(
        supports_catalog=True,
        supports_selection=True,
        max_concurrent_fetch=2,
    )

    _CATALOG: ClassVar[list[Component]] = [
        Component(
            component_id="sales-by-region",
            origin="mock-bi",
            name="各地区销售额",
            schema=ComponentSchema(
                kind="bi.semantic",
                table="sales",
                measures=["sales"],
                dimensions=["region"],
            ),
        ),
        Component(
            component_id="revenue-by-month",
            origin="mock-bi",
            name="各月收入",
            schema=ComponentSchema(
                kind="bi.semantic",
                table="revenue",
                measures=["revenue"],
                dimensions=["month"],
            ),
        ),
    ]

    _current_selection = "sales-by-region"

    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """Return the widget catalog (verb: get_catalog). RLS via ctx."""
        return [c.model_copy(deep=True) for c in self._CATALOG]

    async def get_selection(self, ctx: SessionContext) -> ComponentData:
        """Return the user's current widget selection (verb: get_selection)."""
        return ComponentData(kind="bi.selection", component_id=self._current_selection)

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Return a single widget by id."""
        for c in self._CATALOG:
            if c.component_id == component_id:
                return c.model_copy(deep=True)
        raise KeyError(component_id)

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, object]
    ) -> ComponentData:
        """Fetch data for a widget (verb: get_component_data). RLS via ctx.auth_token."""
        if component.component_id == "sales-by-region":
            return ComponentData(
                kind="bi.table",
                columns=["地区", "销售额"],
                rows=[["华北", 1200], ["华南", 980], ["华东", 1500], ["华西", 1100]],
            )
        return ComponentData(
            kind="bi.table",
            columns=["月份", "收入"],
            rows=[["1月", 4200], ["2月", 4500], ["3月", 5100]],
        )

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData:
        """Refine an already-fetched widget (verb: refine_component). Stubbed."""
        return await self.get_component_data(ctx, component, {})

    async def get_semantic_model(
        self, ctx: SessionContext, component: Component
    ) -> ComponentSchema:
        """Fetch the semantic model of a widget (verb: get_semantic_model)."""
        return component.schema_
