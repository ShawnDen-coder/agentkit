# CODEBUDDY.md

This file provides guidance to CodeBuddy Code when working with code in this repository.

## What this is

AgentKit is a transferable, embeddable agent framework for data-driven tools (BI dashboards
now; DCC hosts like Maya/UE/PySide later), modeled on OpenBB Workspace. Portability rests on
two frozen, versioned "narrow waists"; domain semantics live in swappable profile packages.

The authoritative design lives in `agentkit-architecture.md` (Chinese, ~1100 lines) and
`docs/contracts.md` (the frozen-contract surface + versioning policy). **Read those before
changing anything in `packages/agentkit-protocol`** — the contracts are intentionally frozen.

## Current repo state

**`packages/agentkit-protocol`** (M1) and **`packages/agentkit-runtime`** (M2) are
implemented. `agentkit-runtime` ships `LanggraphOrchestrator`, the `Orchestrator` Protocol
impl: it drives a langchain v1 `create_agent` graph (agent↔tools loop, `recursion_limit`
budget), routes backend-sync verbs to the adapter and frontend verbs to a
`CopilotFunctionCall` via `FrontendActionRequested` (the stateless equivalent of
`interrupt()`), and streams the 6 SSE events. The README, `pyproject.toml`
(`[tool.uv.sources]`), `docs/contracts.md`, and code docstrings still reference packages that
do **not** yet exist in the repo: `agentkit-bi`, `agentkit-mock-app`, `agentkit-cli`,
`agentkit-mcp-gateway`, `agentkit-adapter-*`. Treat those as the planned layout
(milestones M3–M8+), not present code. The README marking `agentkit-bi` as "M1 ✅" is ahead of
the actual tree. `PROTOCOL_VERSION = "0.2.0"` in `agentkit_protocol.models`.

## Commands

Task runner is `just` (via `rust-just`), invoked through uvx. uv workspace; packages live
under `packages/`. Python `>=3.10,<3.14.99`; dev/test on 3.10 (min), CI matrix 3.10–3.14.

```bash
uvx --from rust-just just init        # sync deps + install pre-commit hooks
uvx --from rust-just just lint        # ruff check --fix + ruff format + ruff check
uvx --from rust-just just test        # pytest on dev Python (3.10), with --cov=agentkit_protocol
uvx --from rust-just just test-all    # pytest across 3.10..3.14
uvx --from rust-just just docs        # mkdocs serve (group docs)
uvx --from rust-just just build       # uv build --all-packages
uvx --from rust-just just add-package <name>   # scaffold a new workspace package
```

Run a single test (the justfile recipes always run all of `packages/` with coverage; for one
test, call pytest directly through uv — same pattern for protocol and runtime test paths):

```bash
uv run --all-packages --all-groups --python 3.10 pytest \
  packages/agentkit-protocol/tests/test_models.py::test_sse_to_sse_contract -v
```

Ruff config (`.ruff.toml`): line-length 120, target py310, single-line imports
(`force-single-line`, two blank lines after imports), google docstring convention. Imports
must be at module top level (`PLC0415` is enforced; only `scripts/**` is exempt). `ruff` also
selects `B`, `C4`, `D`, `UP`, `RUF`, `SIM`. Pre-commit adds `uv-lock`, `yamlfmt`,
`check-github-workflows`, `actionlint` (note: there is **no** ruff pre-commit hook — lint runs
via `just lint` and CI).

**Coverage gotcha:** `just test` / `just test-version` pass `--cov=agentkit_protocol` only
(justfile `package_name := "agentkit_protocol"`). Runtime code gets **no** coverage from the
recipes; to cover both packages, call pytest directly with
`--cov=agentkit_protocol --cov=agentkit_runtime`.

## Examples

`example/` holds two runnable deployment demos that prove the wire contract is the stable
seam: same `agentkit_protocol` contracts, same Option B state machine, two deployment modes.
Both entry points now drive `LanggraphOrchestrator` (M2) with an OpenRouter LLM
(`example/_common/openrouter.py`); `example/_common/fake_orchestrator.py` is retained as a
scripted, no-API-key `Orchestrator` impl.

- `example/fastapi-bi/` — C&S over HTTP+SSE (`to_sse()`); browser frontend handles the
  FunctionCall round-trip by re-POSTing `role=tool`.
- `example/pyside-dcc/` — in-process `BaseSSE` object consumption (no serialization); Qt UI;
  round-trip via re-calling `run()` with `role=tool`.

Run with ephemeral deps (no venv pollution), needs `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
uv run --with fastapi --with uvicorn --with langchain-openai python example/fastapi-bi/backend.py
uv run --with pyside6 --with qasync --with langchain-openai python example/pyside-dcc/app.py
```

Example code is linted (`.ruff.toml` includes `example/**`); UI display text is Chinese,
docstrings/comments and wire-protocol values stay English.

## Architecture — the two narrow waists

1. **`ComponentAdapter` Protocol** (`agentkit_protocol.protocols`) — backend ↔ host tool. The only
   contract a vendor adapter implements. Methods map 1:1 to backend-sync verbs
   (`list_components`, `get_component_data`, `refine_component`, `get_semantic_model`, …).
2. **SSE protocol** (`agentkit_protocol.models`) — BI frontend ↔ agent backend. Six events:
   `copilotMessageChunk`, `copilotStatusUpdate`, `copilotMessageArtifact`, `copilotFunctionCall`,
   `copilotCitationCollection`, `copilotPromptSuggestions`. `BaseSSE.to_sse()` →
   `{"event", "data"}`; `event` is a `ClassVar` discriminator (not duplicated in `data`).

**Option B (the core design choice):** data / skill / MCP calls run as **backend sync** calls
inside one request (single SSE stream, multi-hop within the request, `MAX_HOPS` budget). The
`FunctionCall` round-trip (yield `CopilotFunctionCall` → disconnect → frontend executes →
re-POST `role=tool` result → resume) is **reserved for frontend UI actions only**
(`add_component_to_dashboard`, `update_component_in_dashboard`, `manage_navigation_bar`,
`assign_tasks_to_agents`). This is the main divergence from OpenBB, which routes all verbs
through the frontend round-trip.

**Statelessness:** the backend keeps no state; all state lives in `request.messages`. `Message.role`
∈ `{human, tool, assistant, system}` drives the state machine (§6.3): `role=human` runs the
agent; `role=tool` only appears as a frontend UI-action result returning from the round-trip.

### The envelope mechanism (how "core doesn't parse content" works)

Core is **domain-neutral** (depends only on `pydantic` + `xxhash`). `ComponentSchema`,
`ComponentData`, `Refinement`, `Artifact`, and the `*Capabilities` models are **polymorphic
envelopes**: a `kind: str` discriminator + `extra="allow"`. Core never reads their content;
profiles subclass with typed fields.

For subclass fields to survive JSON round-trip through the opaque base, core uses
`SerializeAsAny[ComponentSchema]` (on `Component.schema_`) / `SerializeAsAny[Artifact]` (on
`CopilotMessageArtifact.artifact`). Pattern:
adapter constructs a profile-typed subclass → `model_dump_json()` serializes profile fields →
core reparses as the opaque base (profile fields kept via `extra="allow"`) → profile code
downcasts back with `BiSemanticModel.model_validate(component.schema_.model_dump())`.

**`schema_` alias:** the Python attribute is `schema_` (trailing underscore avoids shadowing
`BaseModel.schema`); it serializes to the wire key `schema`. This is the only aliased field.

### Verb catalogue

`STANDARD_VERBS` (11, frozen in `agentkit_protocol.verbs`): 7 backend
(`get_component_data`, `refine_component`, `get_catalog`, `get_selection`, `get_semantic_model`,
`get_skill_content`, `execute_tool`) + 4 frontend (the UI actions above). `VerbSpec` is frozen
(`extra="forbid"`). Core also ships the binding/alias **declaration primitives**: `VerbBinding`
(name + handler), `VerbAlias` (name -> target, no handler - lets profiles declare aliases like
`get_widget_data` -> `get_component_data` without depending on runtime), and the `VerbBindings`
lookup container. The live entry-point registry (populating that container from skill / MCP
gateways) is M4/M6; until then `agentkit-runtime` binds the 11 verbs to langchain
`StructuredTool`s directly via `verb_tools()` (`agentkit_runtime.tools`). LLM tool definitions
are built by the orchestrator from `VerbSpec` directly (langchain tool format); there is no
`ToolDef`/`verb_to_tool` in core, and no `executes_on` exposed to the LLM.

### The runtime layer (`agentkit-runtime`, M2)

`LanggraphOrchestrator` (`agentkit_runtime.orchestrator`) holds a langchain `BaseChatModel` + a
`ComponentAdapter` and compiles a `create_agent` graph once (reused across requests). `run()`
is an async generator mapping `astream_events(version="v2")` onto the 6 SSE events. Non-obvious
invariants a future change must preserve:

- **Frontend round-trip is a raised exception, not `interrupt()`.** Frontend-verb tools raise
  `FrontendActionRequested` (`agentkit_runtime.tools`); `run()` catches it, yields a
  `CopilotFunctionCall`, and ends the stream. langgraph `interrupt()` would require a
  checkpointer, which would break the frozen "all state in `request.messages`" contract.
- **`ToolErrorMiddleware`** (wired in `LanggraphOrchestrator.__init__`) converts
  `NotImplementedError` (the skill/MCP stubs in `_get_skill_content` / `_execute_tool`) into an
  error `ToolMessage` for LLM recovery, and lets `FrontendActionRequested` propagate. Add new
  unimplemented-verb stubs by raising `NotImplementedError`, not by returning an error string.
- **3.10 streaming constraint.** Side-channel `status`/`artifact` events are emitted with
  `adispatch_custom_event` (config-explicit, 3.10-safe) and consumed via
  `astream_events(version="v2")` `on_custom_event`. **Do not** use `get_stream_writer` /
  `stream_mode="custom"` — it is 3.11+-async-only (contextvar) and the project supports 3.10.
- **`recursion_limit` = `max_hops * 2 + 2`** (each agent↔tools round is 2 super-steps: agent
  node + tools node, plus the final answering agent step). On `GraphRecursionError`, `run()`
  yields a graceful "已达调用上限" chunk and ends the stream.

### Auth seam (above the waists, no `PROTOCOL_VERSION` bump)

`agentkit_protocol.auth` defines transport-agnostic contracts: `Authenticator` (→ `Principal`,
raise `AuthenticationError`/401) and `Authorizer` (per-verb RLS, raise
`AuthorizationError`/403), plus `AuthContext`/`Principal`/`AuthzAction` and the bridge
`session_from_principal`. Auth runs **before** the SSE/orchestrator path, so it is not part of
either narrow waist. Users plug in their own mechanism (JWT/OAuth2/API-key/mTLS/SSO); core
ships only `AllowAllAuthorizer`/`DenyAllAuthorizer` for tests.

**Auth-token transport invariant (§10):** `SessionContext.auth_token` (and `Principal.auth_token`)
is `SecretStr` with `exclude=True` — it travels via the HTTP `Authorization` header (extracted
and injected by the FastAPI layer), **never** the request body, and is never serialized into
`model_dump()`/JSON/logs. Adapters read it via `ctx.auth_token.get_secret_value()` and fetch
data under the user's identity, never a service account. Keep this invariant when touching
`SessionContext`/`Principal` or adding fields.

### Package boundary rules (§C.1)

These are enforced by design intent, not tooling — honor them when adding packages:

1. **Adapters depend on core + their profile, never runtime.** (BI adapter → core + `agentkit-bi`.)
2. **Runtime never statically depends on any adapter** — discovered via the `agentkit.adapters`
   entry-point group at runtime.
3. **Core has zero framework deps** (only `pydantic` + `xxhash`). `langchain` enters only at the
   runtime layer (`agentkit-runtime` — orchestrator holds a `BaseChatModel` directly), never
   the contracts.

Profiles (`agentkit-bi`, future `agentkit-dcc`) version independently of `PROTOCOL_VERSION`.

## Frozen-contract discipline

Anything in `docs/contracts.md` (the 6 SSE events, `QueryRequest`/`Message`/`SessionContext`,
`Component`/`ComponentSchema` envelope, `ComponentAdapter` Protocol, the 11-verb catalogue,
`to_sse()` shape, the auth seam) is **frozen**. Changing it bumps `PROTOCOL_VERSION` (semver:
patch=clarification/additive optional; minor=additive event/field/verb/kind; major=breaking)
and requires updating `docs/contracts.md` **and** `agentkit-architecture.md`. SSE events and
request models use `extra="forbid"` (strict); envelopes use `extra="allow"` (forward-compat).
SSE events that don't apply should be ignored by consumers (forward-compat), not removed.

The contract tests in `packages/agentkit-protocol/tests/` (`test_models.py`, `test_protocols.py`,
`test_verbs.py`, `test_testing.py`) are the executable spec for the waists — they encode the
round-trip, serialization, verb-catalogue, and adapter-Protocol invariants above. The runtime
package has its own `packages/agentkit-runtime/tests/test_smoke.py` (no real LLM call — uses a
scripted `FakeMessagesListChatModel` to verify the `create_agent` + `astream_events` path,
frontend-verb interrupt, and `GraphRecursionError` handling).

## Versioning & release

[cocogitto](https://github.com/cocogitto/cocogitto) (`cog.toml`) manages monorepo + per-package
versions and changelogs. The `version-bump.yaml` workflow auto-bumps on push to `master`/`main`
(committing as `cog-bot`); `package-release.yaml` builds only packages whose version tag points
at the current commit (`just build-changed`) and publishes to PyPI + a private server. Tag a
package version (`<pkg>-<ver>`) at the release commit to trigger its build. Conventional Commits
drive the changelog (`ignore_merge_commits = true`, `branch_whitelist = ["master","main"]`).
