# agentkit-core

Domain-neutral protocol + framework core for [agentkit](https://github.com/ShawnDen-coder/agentkit).
Freezes the **two narrow waists** on which portability depends:

- **Waist ② - SSE protocol**: the 6 copilot events + `QueryRequest` / `Message` / `SessionContext`.
- **Waist ① - adapter contract**: `Component` / `ComponentSchema` envelope + `ComponentAdapter` Protocol.

Core is **BI-agnostic and framework-free** (only `pydantic` + `xxhash`). Domain semantics
(`BiSemanticModel`, `DccSchema`, chart artifacts) live in profile packages (`agentkit-bi`,
future `agentkit-dcc`). Core never parses the content of a `ComponentSchema` or `Artifact` -
they flow through as opaque polymorphic envelopes. `langchain` is **not** a dependency; it
enters only at the `LlmClient` layer (M2, `agentkit-llm-langchain`).

See [`docs/contracts.md`](../../docs/contracts.md) for the frozen surface + versioning policy,
and [`agentkit-architecture.md`](../../agentkit-architecture.md) for the full design.

## Contents

| Module | What it freezes |
|---|---|
| `models` | SSE 6 events (`BaseSSE.to_sse()` -> `{"event","data"}`); `QueryRequest`/`Message`/`SessionContext`; domain-neutral `Component`/`ComponentSchema`/`ComponentData`/`Refinement` envelopes; `ComponentParam`/`ComponentCapabilities`/`AdapterCapabilities`/`Field`; generic artifacts (`TextArtifact`/`MarkdownArtifact`/`TableArtifact`/`ErrorArtifact`); `Citation` |
| `protocols` | `ComponentAdapter` (narrow waist ①), `Orchestrator`, `LlmClient` Protocols; `VerbHandler` type |
| `verbs` | `VerbSpec` + 11 standard verbs (`STANDARD_VERBS` = 7 backend-sync `BACKEND_VERBS` + 4 frontend-FunctionCall `FRONTEND_VERBS`) |
| `helpers` | `deterministic_uuid(origin, component_id)` (xxhash, cross-turn stable) |
| `testing` | `CopilotResponse` DSL + `collect_stream` / `query` / `human_message` for contract tests |

`PROTOCOL_VERSION = "0.1.0"`.

## Install

This package is part of the uv workspace; consumers depend on it as `agentkit-core` (dist) /
`agentkit_core` (import). In the monorepo: `uv sync --all-packages --all-groups`.

## Quick example

```python
from agentkit_core import (
    Component,
    ComponentSchema,
    CopilotMessageArtifact,
    TableArtifact,
    deterministic_uuid,
)

# Waist ②: an SSE event serializes to the wire contract.
event = CopilotMessageArtifact(artifact=TableArtifact(columns=["region", "sales"], rows=[["N", 100]]))
assert event.to_sse() == {
    "event": "copilotMessageArtifact",
    "data": '{"artifact":{"kind":"table","columns":["region","sales"],"rows":[["N",100]]}}',
}

# Waist ①: a Component carries an opaque schema envelope. Core does not parse it;
# profiles (agentkit-bi) supply typed schemas like BiSemanticModel (kind="bi.semantic").
component = Component(
    component_id="w1",
    origin="superset",
    name="Sales by Region",
    schema=ComponentSchema(kind="bi.semantic", dimensions=[{"name": "region"}]),
)
roundtripped = Component.model_validate_json(component.model_dump_json(by_alias=True))
assert roundtripped.schema_.kind == "bi.semantic"          # core reads only `kind`
assert "dimensions" in roundtripped.schema_.model_dump()   # profile fields preserved

# Deterministic, cross-turn-stable component UUID.
assert deterministic_uuid("superset", "w1") == deterministic_uuid("superset", "w1")
```

## Design notes

- **Polymorphic envelope**: profile schemas subclass `ComponentSchema` with a `kind` Literal +
  typed fields. The `Component.schema_` field is typed `SerializeAsAny[ComponentSchema] | None`,
  so subclass fields survive JSON round-trip through core (deserialized back as the opaque base
  via `extra="allow"`; profiles downcast with `model_validate`). Same pattern for `Artifact`.
- **`schema_` attribute**: the Python attribute is `schema_` (trailing underscore avoids
  shadowing `BaseModel.schema`); it serializes to the wire key `schema`. This is the only
  aliased field.
- **`AdapterCapabilities` split**: core holds cross-domain flags (`supports_catalog`,
  `supports_selection`, `max_concurrent_fetch`); profiles extend with domain flags (BI:
  `can_filter` / `can_drill` / `can_add_widget` / `supports_semantic_model`).
- **Strict events, open envelopes**: SSE events use `extra="forbid"`; envelopes
  (`ComponentSchema`, `Artifact`, capabilities, `Field`) use `extra="allow"` for forward-compat.

## Status

M1 ✅ - contracts frozen. `Orchestrator` / `LlmClient` are Protocols only (impls in M2);
the live `VerbRegistry`, FastAPI app, and real adapters arrive in later milestones.
