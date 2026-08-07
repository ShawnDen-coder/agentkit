# AgentKit Frozen Contracts (M1)

> M1 freezes the two narrow waists. This document enumerates the frozen surface and
> the versioning policy. Changes to anything listed here require a version bump
> (see [Versioning](#versioning)) and an update to this file + `agentkit-architecture.md`.

`PROTOCOL_VERSION = "0.1.0"` (defined in `agentkit_core`).

## Narrow waist ② — SSE protocol

The wire contract between frontend and backend (Option B). Consumed by FastAPI
`EventSourceResponse`.

### The 6 events

| Event class | Wire `event` name | Payload |
|---|---|---|
| `CopilotMessageChunk` | `copilotMessageChunk` | `text`, `message_id?` |
| `CopilotStatusUpdate` | `copilotStatusUpdate` | `status`, `label?` |
| `CopilotMessageArtifact` | `copilotMessageArtifact` | `artifact` (envelope), `message_id?` |
| `CopilotFunctionCall` | `copilotFunctionCall` | `name`, `arguments` (frontend UI action only) |
| `CopilotCitationCollection` | `copilotCitationCollection` | `citations[]` |
| `CopilotPromptSuggestions` | `copilotPromptSuggestions` | `suggestions[]` |

### Serialization contract

`BaseSSE.to_sse() -> {"event": str, "data": <json string>}`. The `event` name is a
class-level discriminator (not duplicated inside `data`). `data` is
`model_dump_json(by_alias=True, exclude_none=True)` of the payload. SSE events use
`extra="forbid"` (strict).

### Request envelope

- `QueryRequest`: `messages[]`, `session_context`, `protocol_version` (default
  `PROTOCOL_VERSION`), `tools?`, `features?`, `workspace_options?`. Stateless: all
  state lives in `messages`.
- `Message`: `role` ∈ `{human, tool, assistant, system}` drives the state machine
  (§6.3). `role=tool` only for frontend UI-action results (carries `name` + `data`).
- `SessionContext`: `user_identity`, `user_permissions[]`, `workspace_id`, `trace_id`.

## Narrow waist ① — ComponentAdapter contract

The contract a host-tool adapter implements. Discovered via the `agentkit.adapters`
entry-point group; runtime never statically depends on adapters.

### ComponentAdapter Protocol (`agentkit_core.protocols`)

| Member | Kind |
|---|---|
| `origin: str` | attribute |
| `capabilities: AdapterCapabilities` | attribute |
| `async list_components(ctx) -> list[Component]` | method (verb: get_catalog) |
| `async get_component(ctx, component_id) -> Component` | method |
| `async get_component_data(ctx, component, input_args) -> ComponentData` | method (verb: get_component_data) |
| `async refine_component(ctx, component, refinement) -> ComponentData` | method (verb: refine_component) |
| `async get_semantic_model(ctx, component) -> ComponentSchema` | method (verb: get_semantic_model) |

### Domain-neutral abstractions (`agentkit_core.models`)

- `Component`: `component_id`, `origin`, `name`, `params[]`, `capabilities`,
  `schema_` (the schema envelope).
- `ComponentSchema`: polymorphic envelope (`kind: str`, `extra="allow"`). Core never
  parses content. Profiles subclass (`BiSemanticModel`, future `DccSchema`).
- `ComponentData` / `Refinement`: same polymorphic-envelope pattern.
- `AdapterCapabilities` / `ComponentCapabilities`: base + `extra="allow"`; profiles
  extend. Core flags: `supports_catalog`, `supports_selection`, `max_concurrent_fetch`.
- `Field`: shared generic field (BI dimensions/measures, future DCC attributes).

### The envelope mechanism (how "core doesn't parse content" actually works)

Profile schemas (e.g. `BiSemanticModel`) are subclasses of the core envelope
(`ComponentSchema`) with typed fields. Core fields that hold them use
`SerializeAsAny[ComponentSchema]` so subclass fields survive JSON round-trip:

- Adapter constructs `BiSemanticModel(...)` and sets `component.schema_`.
- `Component.model_dump_json()` serializes the BI fields (via `SerializeAsAny`).
- `Component.model_validate_json(...)` reparses `schema_` as the opaque base
  (`ComponentSchema`); BI fields are preserved via `extra="allow"`.
- BI code downcasts back: `BiSemanticModel.model_validate(component.schema_.model_dump())`,
  or via `Widget.semantic_model` / `BiAdapter.as_bi_schema`.

### `schema_` attribute name

The Python attribute is `schema_` (trailing underscore) to avoid shadowing
`BaseModel.schema`; it serializes to the wire key `schema` (alias). This is the only
aliased field in M1.

## Verb catalogue (11)

Per Option B (§D.4), verbs split by execution location:

- **Backend sync** (7): `get_component_data`, `refine_component`, `get_catalog`,
  `get_selection`, `get_semantic_model`, `get_skill_content`, `execute_tool`.
- **Frontend FunctionCall** (4): `add_component_to_dashboard`,
  `update_component_in_dashboard`, `manage_navigation_bar`, `assign_tasks_to_agents`.

M1 freezes the catalogue (names + input schemas + category) in `STANDARD_VERBS`. The
live `VerbRegistry` (binding handlers) is wired in M2. BI aliases
(`get_widget_data` → `get_component_data`, etc.) and `export_artifact` are declared in
`agentkit_bi`.

## What is NOT in M1 (deferred)

- `Orchestrator` / `LlmClient` — Protocol only; impls in M2 (`StatelessOrchestrator`,
  `LangChainLlmClient`).
- Live `VerbRegistry`, FastAPI app, SSE endpoint — M2.
- Real adapter (Superset) — M3. Multi-hop (`MAX_HOPS`) — M4. Skills — M5. MCP — M6.
- **Auth token transport (open gap §5.1 vs §10)**: `SessionContext` does not yet model
  the BI auth token required for Option B backend-fetch. Deferred to M2 (L3 integration
  layer); may extend `SessionContext` (minor version bump). Adapters must not assume a
  token field exists yet.
- `BiSemanticModel.calculated_fields` is optional (default `None`) pending §14 Q1
  resolution at M3 (Superset + Metabase + Looker comparison).

## Versioning

Semantic versioning on `PROTOCOL_VERSION`:

- **Patch**: clarifications, additive optional fields that don't break existing parsers.
- **Minor**: additive (new event, new optional field, new verb, new envelope `kind`).
  Existing consumers must ignore unknown kinds/events (forward-compat).
- **Major**: breaking (removed/renamed event, changed payload shape of an existing
  event, changed `ComponentAdapter` method signature, changed envelope `kind` values).

Two narrow waists are the strong constraint: any change to them bumps the version and
updates this file + `agentkit-architecture.md`. Profile packages (`agentkit-bi`,
future `agentkit-dcc`) version independently of `PROTOCOL_VERSION`.
