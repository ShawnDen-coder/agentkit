"""Contract tests for agentkit-bi profile (schemas, artifacts, capabilities, adapter)."""

from __future__ import annotations

import json

from agentkit_bi import BI_EXTRA_VERBS
from agentkit_bi import BI_VERB_ALIASES
from agentkit_bi import BiAdapter
from agentkit_bi import BiAdapterCapabilities
from agentkit_bi import BiRefinement
from agentkit_bi import BiSemanticModel
from agentkit_bi import CalculatedField
from agentkit_bi import ChartArtifact
from agentkit_bi import DrillPath
from agentkit_bi import FilterSpec
from agentkit_bi import Widget
from agentkit_bi import WidgetCapabilities
from agentkit_bi import WidgetData
from agentkit_bi import build_bi_system_prompt
from agentkit_core import Component
from agentkit_core import ComponentAdapter
from agentkit_core import Field
from agentkit_core import Refinement


# -- BiSemanticModel + envelope -------------------------------------------


def test_bi_semantic_model_kind() -> None:
    """BiSemanticModel discriminates by kind='bi.semantic' and carries BI fields."""
    sm = BiSemanticModel(
        dimensions=[Field(name="region", dtype="string")],
        measures=[Field(name="sales", dtype="number")],
        time_grains=["day", "month"],
        drill_paths=[DrillPath(from_field="region", to_fields=["city"])],
    )
    assert sm.kind == "bi.semantic"
    assert sm.dimensions[0].name == "region"
    assert sm.time_grains == ["day", "month"]


def test_bi_semantic_model_envelope_roundtrip() -> None:
    """BiSemanticModel survives round-trip through core's opaque ComponentSchema envelope."""
    sm = BiSemanticModel(
        dimensions=[Field(name="region", dtype="string")],
        measures=[Field(name="sales", dtype="number")],
        calculated_fields=[CalculatedField(name="margin", expression="sales - cost")],
    )
    w = Widget(component_id="w1", origin="superset", name="Sales", schema=sm)
    j = w.model_dump_json(by_alias=True)
    reparsed = Component.model_validate_json(j)
    assert reparsed.schema_ is not None
    assert reparsed.schema_.kind == "bi.semantic"
    # BI downcast recovers the typed model with all fields
    bi = BiSemanticModel.model_validate(reparsed.schema_.model_dump())
    assert bi.dimensions[0].name == "region"
    assert bi.calculated_fields[0].name == "margin"


def test_widget_semantic_model_accessor() -> None:
    """Widget.semantic_model downcasts the opaque schema envelope to BiSemanticModel."""
    sm = BiSemanticModel(measures=[Field(name="sales")])
    w = Widget(component_id="w1", origin="superset", name="Sales", schema=sm)
    assert isinstance(w.semantic_model, BiSemanticModel)
    assert w.semantic_model.measures[0].name == "sales"
    # None when no schema
    w2 = Widget(component_id="w2", origin="superset", name="X")
    assert w2.semantic_model is None


def test_calculated_fields_optional() -> None:
    """calculated_fields defaults to None (Superset leaves empty; Looker fills)."""
    sm = BiSemanticModel()
    assert sm.calculated_fields is None


# -- Artifacts / data / refinement ----------------------------------------


def test_chart_artifact_serialize() -> None:
    """ChartArtifact serializes with kind='chart' and axis mappings."""
    chart = ChartArtifact(chart_type="bar", x_key="region", y_keys=["sales"], title="Sales")
    payload = json.loads(chart.model_dump_json())
    assert payload["kind"] == "chart"
    assert payload["chart_type"] == "bar"
    assert payload["y_keys"] == ["sales"]


def test_widget_data_envelope() -> None:
    """WidgetData is a ComponentData envelope (kind='bi.data') with columns/rows."""
    wd = WidgetData(columns=["region", "sales"], rows=[["north", 100]], row_count=1)
    assert wd.kind == "bi.data"
    payload = json.loads(wd.model_dump_json())
    assert payload["columns"] == ["region", "sales"]
    assert payload["row_count"] == 1


def test_bi_refinement_envelope() -> None:
    """BiRefinement round-trips through the opaque Refinement envelope."""
    r = BiRefinement(
        filters=[FilterSpec(field="region", operator="=", values=["north"])],
        measures=["sales"],
        time_grain="month",
    )
    assert r.kind == "bi.refine"
    reparsed = Refinement.model_validate_json(r.model_dump_json())
    assert reparsed.kind == "bi.refine"
    bi = BiRefinement.model_validate(reparsed.model_dump())
    assert bi.filters[0].field == "region"
    assert bi.time_grain == "month"


# -- Capabilities ---------------------------------------------------------


def test_bi_adapter_capabilities_extend_core() -> None:
    """BiAdapterCapabilities inherits core flags and adds BI-specific ones."""
    cap = BiAdapterCapabilities(
        supports_catalog=True,
        can_filter=True,
        can_drill=True,
        can_add_widget=False,
        supports_semantic_model=True,
        max_concurrent_fetch=4,
    )
    assert cap.supports_catalog is True
    assert cap.can_drill is True
    assert cap.max_concurrent_fetch == 4


def test_widget_capabilities() -> None:
    """WidgetCapabilities carries per-widget BI capability flags."""
    cap = WidgetCapabilities(can_filter=True, can_drill=False, can_export=True)
    assert cap.can_filter is True
    assert cap.can_export is True


# -- BiAdapter + ComponentAdapter Protocol --------------------------------


class _StubBiAdapter(BiAdapter):
    """Minimal BiAdapter subclass for Protocol conformance testing."""

    origin = "stub"
    capabilities = BiAdapterCapabilities(supports_catalog=True, can_filter=True)

    async def list_components(self, ctx):
        """Return empty catalog."""
        return []

    async def get_component(self, ctx, component_id):
        """Return None (stub)."""
        return None

    async def get_component_data(self, ctx, component, input_args):
        """Return None (stub)."""
        return None

    async def refine_component(self, ctx, component, refinement):
        """Return None (stub)."""
        return None

    async def get_semantic_model(self, ctx, component):
        """Return None (stub)."""
        return None


def test_bi_adapter_is_component_adapter() -> None:
    """A BiAdapter subclass is structurally a ComponentAdapter (runtime_checkable)."""
    stub = _StubBiAdapter()
    assert isinstance(stub, ComponentAdapter)
    assert stub.origin == "stub"


def test_bi_adapter_downcast_helpers() -> None:
    """BiAdapter.as_widget / as_bi_refinement / as_bi_schema downcast opaque envelopes."""
    sm = BiSemanticModel(measures=[Field(name="sales")])
    w = Widget(component_id="w1", origin="superset", name="Sales", schema=sm)
    # round-trip through base Component to simulate crossing the core boundary
    base = Component.model_validate(w.model_dump(by_alias=True))
    restored = BiAdapter.as_widget(base)
    assert isinstance(restored, Widget)
    assert restored.semantic_model is not None
    assert restored.semantic_model.measures[0].name == "sales"

    bi_r = BiRefinement(filters=[FilterSpec(field="x", operator="=", values=[1])])
    base_r = Refinement.model_validate(bi_r.model_dump())
    assert BiAdapter.as_bi_refinement(base_r).filters[0].field == "x"

    assert BiAdapter.as_bi_schema(None) is None
    assert BiAdapter.as_bi_schema(base.schema_).measures[0].name == "sales"


# -- Verbs + prompt -------------------------------------------------------


def test_bi_verb_aliases() -> None:
    """BI verb aliases map BI-flavored names to canonical core verbs."""
    assert BI_VERB_ALIASES["get_widget_data"] == "get_component_data"
    assert BI_VERB_ALIASES["refine_widget"] == "refine_component"
    assert BI_VERB_ALIASES["get_widget_catalog"] == "get_catalog"
    assert any(v.name == "export_artifact" for v in BI_EXTRA_VERBS)


def test_build_bi_system_prompt_no_widgets() -> None:
    """With no widgets, the prompt guides the user instead of fabricating data."""
    cap = BiAdapterCapabilities(supports_catalog=True, can_filter=True)
    prompt = build_bi_system_prompt(capabilities=cap, components=None)
    assert "fabricate" in prompt.lower()


def test_build_bi_system_prompt_with_widgets() -> None:
    """With widgets + skills + toggles, the prompt lists all of them."""
    cap = BiAdapterCapabilities(supports_catalog=True, can_filter=True)
    prompt = build_bi_system_prompt(
        capabilities=cap,
        components=[Widget(component_id="w1", origin="superset", name="Sales")],
        active_skills=["variance-analysis"],
        toggles={"anomaly": True},
    )
    assert "Sales" in prompt
    assert "variance-analysis" in prompt
    assert "anomaly" in prompt
