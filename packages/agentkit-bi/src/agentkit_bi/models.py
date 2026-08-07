"""agentkit-bi: BI domain profile (schemas, data, capabilities, refinements).

These types are BI-specific realizations of agentkit-core's domain-neutral envelopes:
  * BiSemanticModel  -> ComponentSchema (kind="bi.semantic")
  * WidgetData       -> ComponentData   (kind="bi.data")
  * BiRefinement     -> Refinement      (kind="bi.refine")
  * WidgetCapabilities / BiAdapterCapabilities -> extend core capability bases

Core treats all of these as opaque envelopes; BI code downcasts via ``model_validate``.
"""

from __future__ import annotations

from typing import Any
from typing import Literal

from agentkit_core import AdapterCapabilities
from agentkit_core import Component
from agentkit_core import ComponentCapabilities
from agentkit_core import ComponentData
from agentkit_core import ComponentSchema
from agentkit_core import Field
from agentkit_core import Refinement
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field as PydanticField


__all__ = [
    "BiAdapterCapabilities",
    "BiRefinement",
    "BiSemanticModel",
    "CalculatedField",
    "DrillPath",
    "FilterSpec",
    "Widget",
    "WidgetCapabilities",
    "WidgetData",
    "WidgetParam",
]


# ---------------------------------------------------------------------------
# BI primitives
# ---------------------------------------------------------------------------


class FilterSpec(BaseModel):
    """A filter on a BI field."""

    model_config = ConfigDict(extra="allow")

    field: str
    operator: str  # "=" | "!=" | "in" | "not_in" | "between" | "like" | ...
    values: list[Any] = PydanticField(default_factory=list)


class DrillPath(BaseModel):
    """A drill-down path from one field to a set of finer fields."""

    model_config = ConfigDict(extra="allow")

    from_field: str
    to_fields: list[str] = PydanticField(default_factory=list)


class CalculatedField(BaseModel):
    """A derived/computed measure (Looker-style). Optional - Superset adapters leave empty."""

    model_config = ConfigDict(extra="allow")

    name: str
    expression: str  # the tool's native expression dialect
    dtype: str | None = None


# ---------------------------------------------------------------------------
# BI schema + data + refinement (profile realizations of core envelopes)
# ---------------------------------------------------------------------------


class BiSemanticModel(ComponentSchema):
    """Typed BI semantic model. Flows through Component.schema_ as an opaque envelope."""

    kind: Literal["bi.semantic"] = "bi.semantic"
    dimensions: list[Field] = PydanticField(default_factory=list)
    measures: list[Field] = PydanticField(default_factory=list)
    available_filters: list[FilterSpec] = PydanticField(default_factory=list)
    time_grains: list[str] = PydanticField(default_factory=list)  # day/week/month/quarter/year
    drill_paths: list[DrillPath] = PydanticField(default_factory=list)
    # Open question §14 Q1: derived measures. Optional - Looker fills, Superset leaves empty.
    # Revisit at M3 once Superset + Metabase + Looker schemas are compared.
    calculated_fields: list[CalculatedField] | None = None


class WidgetData(ComponentData):
    """Typed BI data payload (tabular). Flows through get_component_data returns."""

    kind: Literal["bi.data"] = "bi.data"
    columns: list[str] = PydanticField(default_factory=list)
    rows: list[list[Any]] = PydanticField(default_factory=list)
    row_count: int | None = None


class BiRefinement(Refinement):
    """Typed BI refinement for refine_component (filter / drill / swap measure / time grain)."""

    kind: Literal["bi.refine"] = "bi.refine"
    filters: list[FilterSpec] = PydanticField(default_factory=list)
    drill: DrillPath | None = None
    measures: list[str] | None = None  # measure names to swap to
    time_grain: str | None = None


# ---------------------------------------------------------------------------
# BI capabilities (extend core capability bases)
# ---------------------------------------------------------------------------


class WidgetCapabilities(ComponentCapabilities):
    """Per-widget capability flags (the BI view of ComponentCapabilities)."""

    can_filter: bool = False
    can_drill: bool = False
    can_export: bool = False


class BiAdapterCapabilities(AdapterCapabilities):
    """Per-BI-tool capability flags. Drives which verbs the runtime exposes (§5.2)."""

    can_filter: bool = False  # refine_component usable
    can_drill: bool = False
    can_add_widget: bool = False  # add_component_to_dashboard usable
    supports_semantic_model: bool = False  # get_semantic_model usable


# ---------------------------------------------------------------------------
# Widget: BI convenience view of Component
# ---------------------------------------------------------------------------


class WidgetParam(BaseModel):
    """A parameter a BI widget accepts. Convenience alias for ComponentParam fields."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    value: Any | None = None
    default: Any | None = None
    required: bool = False
    label: str | None = None


class Widget(Component):
    """BI view of a Component. Adds a typed ``semantic_model`` accessor.

    A Widget IS-A Component, so BI adapters may return Widget instances where the
    ComponentAdapter Protocol expects Component. ``schema_`` still carries the
    BiSemanticModel envelope; ``semantic_model`` downcasts it for type-safe BI access.
    """

    @property
    def semantic_model(self) -> BiSemanticModel | None:
        """Downcast the opaque ``schema_`` envelope to a typed BiSemanticModel (or None)."""
        if self.schema_ is None:
            return None
        if isinstance(self.schema_, BiSemanticModel):
            return self.schema_
        return BiSemanticModel.model_validate(self.schema_.model_dump())
