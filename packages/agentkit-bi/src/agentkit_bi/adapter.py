"""BiAdapter: convenience base for BI adapter authors.

BI adapters subclass ``BiAdapter`` and implement the abstract async methods. Method
signatures mirror the ``ComponentAdapter`` Protocol exactly (base types in/out), so any
``BiAdapter`` subclass is structurally a valid ``ComponentAdapter`` - the runtime
discovers it via the ``agentkit.adapters`` entry-point group with no static dependency.

BI flavor comes from: the ``BiAdapterCapabilities`` capabilities, the BI-typed
instances adapters construct internally (Widget / WidgetData / BiSemanticModel), and
the downcast helpers below.
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from typing import Any

from agentkit_core import Component
from agentkit_core import ComponentData
from agentkit_core import ComponentSchema
from agentkit_core import Refinement
from agentkit_core import SessionContext

from agentkit_bi.models import BiAdapterCapabilities
from agentkit_bi.models import BiRefinement
from agentkit_bi.models import BiSemanticModel
from agentkit_bi.models import Widget


__all__ = ["BiAdapter"]


class BiAdapter(ABC):
    """Convenience base for BI adapters. Subclass and implement the abstract methods.

    Class attributes:
        origin: the BI tool identifier ("superset" | "metabase" | ...).
        capabilities: a ``BiAdapterCapabilities`` declaring what this BI supports.
    """

    origin: str  # set by subclass
    capabilities: BiAdapterCapabilities

    @abstractmethod
    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """Return the catalog of available widgets/datasets (verb: get_catalog)."""
        ...

    @abstractmethod
    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Return a single widget by id."""
        ...

    @abstractmethod
    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, Any]
    ) -> ComponentData:
        """Fetch data for a widget (verb: get_component_data). RLS enforced via ctx."""
        ...

    @abstractmethod
    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData:
        """Refine an already-fetched widget via its semantic model (verb: refine_component)."""
        ...

    @abstractmethod
    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema:
        """Fetch the semantic model of a widget (verb: get_semantic_model)."""
        ...

    # --- BI downcast helpers (core treats these as opaque envelopes) ---

    @staticmethod
    def as_widget(component: Component) -> Widget:
        """Downcast a Component to a Widget (typed BI view)."""
        return Widget.model_validate(component.model_dump(by_alias=True))

    @staticmethod
    def as_bi_refinement(refinement: Refinement) -> BiRefinement:
        """Downcast an opaque Refinement envelope to a typed BiRefinement."""
        return BiRefinement.model_validate(refinement.model_dump())

    @staticmethod
    def as_bi_schema(schema: ComponentSchema | None) -> BiSemanticModel | None:
        """Downcast an opaque ComponentSchema envelope to a typed BiSemanticModel."""
        if schema is None:
            return None
        if isinstance(schema, BiSemanticModel):
            return schema
        return BiSemanticModel.model_validate(schema.model_dump())
