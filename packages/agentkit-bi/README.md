# agentkit-bi

BI profile for [agentkit](https://github.com/ShawnDen-coder/agentkit). Carries the
BI domain semantics that the domain-neutral `agentkit-core` deliberately omits.

## Contents

- **`BiSemanticModel`** — typed BI schema (dimensions / measures / drill paths / time
  grains / filters / calculated fields), a `ComponentSchema` envelope (`kind="bi.semantic"`).
- **`Widget`** — BI convenience view of `Component`, with a typed `semantic_model` accessor.
- **`WidgetData`** — typed BI data payload (columns / rows), a `ComponentData` envelope.
- **`BiRefinement`** — typed refinement (filters / drill / measure swap / time grain).
- **`BiAdapterCapabilities` / `WidgetCapabilities`** — BI capability flags extending core.
- **`ChartArtifact`** — BI chart artifact (`kind="chart"`).
- **`BiAdapter`** — convenience base for BI adapter authors.
- **`build_bi_system_prompt`** — BI system prompt builder (§6.5).

Core never parses `BiSemanticModel` content — it flows through `Component.schema_` as
an opaque envelope (see `agentkit_core` design notes).
