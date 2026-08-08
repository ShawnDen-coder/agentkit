# AgentKit Frozen Contracts

> The two narrow waists + supporting contracts. This document enumerates the frozen
> surface and the versioning policy. Changes to anything listed here require a version
> bump (see [Versioning](#versioning)) and an update to this file + `agentkit-architecture.md`.

`PROTOCOL_VERSION = "0.2.0"` (defined in `agentkit_core`).

> **0.2.0 (M2) changes** (additive, backward-compatible):
> - `SessionContext.auth_token: SecretStr | None` (`exclude=True`) - BI auth token for
>   Option B backend-fetch. Transported via HTTP `Authorization` header (FastAPI layer
>   extracts + injects), never the request body; never serialized into `model_dump()` /
>   JSON / logs. Closes the §5.1-vs-§10 gap.
> - `LlmClient` Protocol tightened: `call -> LlmResponse`, `stream -> AsyncIterator[LlmChunk]`,
>   param `functions` -> `tools: list[ToolDef] | None`. New provider-neutral types in
>   `agentkit_core.llm`: `ToolDef`, `LlmChunk`, `LlmToolCall`, `LlmResponse`. Lets the
>   orchestrator route tool calls without depending on any LLM SDK.
>
> **0.1.0 (M1)**: initial freeze - the 6 SSE events, `QueryRequest`/`Message`/`SessionContext`,
> `Component`/`ComponentSchema` envelope, `ComponentAdapter` Protocol, 11-verb catalogue,
> testing DSL.

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
- `SessionContext`: `user_identity`, `user_permissions[]`, `workspace_id`, `trace_id`,
  `auth_token: SecretStr | None` (0.2.0, `exclude=True`). The auth token travels via the
  HTTP `Authorization` header (extracted + injected by the FastAPI layer), NOT the body;
  it is never serialized (excluded from `model_dump()` / JSON / logs). Adapters read it
  via `ctx.auth_token.get_secret_value()`.

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

## Authentication & authorization seam (user-implemented)

Auth runs *before* a request enters the SSE/orchestrator path, so it is **not** part of
either narrow waist and does **not** bump `PROTOCOL_VERSION`. The contracts live in
`agentkit_core.auth` and are **transport-agnostic** (no HTTP type) so one implementation
serves both the web profile (FastAPI) and the DCC profile (PySide/Maya host session).

Users plug in their own mechanism (JWT, OAuth2, API-key, mTLS, studio SSO, ...) by
implementing two Protocols:

- **`Authenticator.authenticate(context: AuthContext) -> Principal`** (async) - verifies
  the caller and returns a `Principal` (`user_identity`, `user_permissions`, delegated
  `auth_token: SecretStr`, `workspace_id`, `metadata`). Raise `AuthenticationError` (-> 401).
- **`Authorizer.authorize(principal, action: AuthzAction) -> None`** (async) - per-verb
  RLS/scope check; return to allow, raise `AuthorizationError` (-> 403). `AuthzAction`
  carries `verb` + `component_id` + `args` for field/row-level decisions.

Supporting types: `AuthContext` (headers/query/cookies/peer bag; `header()` is
case-insensitive), `Principal` (frozen; `auth_token` is `exclude=True` so it is never
serialized), `AuthzAction` (frozen). Trivial dev/test impls: `AllowAllAuthorizer`,
`DenyAllAuthorizer` (a header-trusting `Authenticator` ships in `agentkit-mock-app`).

The app layer bridges a verified `Principal` onto the wire `SessionContext` via
`session_from_principal(principal, *, trace_id, workspace_id=None)`. `SessionContext` is
unchanged (still the RLS passthrough vehicle); the §10 invariants - no service account,
short-lived/unlogged/uncached token - are enforced by the *implementations*, not the seam.

## What is NOT yet implemented (deferred)

- `Orchestrator` / `LlmClient` - Protocol only in 0.1.0; `LlmClient` tightened in 0.2.0.
  `LangChainLlmClient` landed in `agentkit-llm-langchain` (M2); `StatelessOrchestrator`
  (in `agentkit-runtime`) still pending.
- Live `VerbRegistry`, FastAPI app, SSE endpoint - M2. Packages `agentkit-runtime`,
  `agentkit-mock-app`, `agentkit-cli` are scaffolded (M2 in progress); the auth seam
  (`Authenticator`/`Authorizer`/`Principal`/`AuthContext`/`AuthzAction`) is frozen in
  `agentkit_core.auth` (0.2.0+, no `PROTOCOL_VERSION` bump - it is above the waists).
- Real adapter (Superset) - M3. Multi-hop (`MAX_HOPS`) - M4. Skills - M5. MCP - M6.
- `BiSemanticModel.calculated_fields` is optional (default `None`) pending the §14 Q1
  resolution at M3 (Superset + Metabase + Looker comparison).

> Auth-token transport (formerly the §5.1-vs-§10 open gap) is resolved in 0.2.0:
> `SessionContext.auth_token` via `Authorization` header, `exclude=True`. The full
> auth/authz seam (how that token + identity + permissions are derived) is the
> user-implemented `Authenticator`/`Authorizer` above.

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
