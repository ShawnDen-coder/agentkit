# AgentKit

### Overview

A transferable, embeddable agent framework for data-driven tools (BI dashboards now;
DCC hosts like Maya/UE/PySide later). Modeled on OpenBB Workspace: two narrow waists
(a frozen `ComponentAdapter` contract + a frozen SSE protocol) carry the portability;
domain semantics live in swappable profile packages (`agentkit-bi`, future `agentkit-dcc`).

**AgentKit is a langchain/langgraph plugin, not a parallel framework** (0.3.0):
- **Backend is langchain-native** — users write `@tool`, `create_agent`, configure
  checkpointer. The orchestrator uses langgraph's native `interrupt()` for HITL.
- **Frontend is wire-native** — 6 SSE events + `FunctionCall` round-trip, no langchain.
- **Both stateful (checkpointer + `thread_id`) and stateless modes supported.**
- **Option B**: data/skill/MCP are backend-sync calls; the FunctionCall loop is reserved
  for frontend UI actions only.

See [`agentkit-architecture.md`](agentkit-architecture.md) for the full design (appendix E
covers the 0.3.0 plugin repositioning) and [`docs/contracts.md`](docs/contracts.md) for the
frozen-contract surface (`PROTOCOL_VERSION = "0.3.0"`).

### Workspace layout

uv workspace; packages live under `packages/`.

| Package | Description | Milestone |
|---------|-------------|-----------|
| `agentkit-protocol` | Domain-neutral protocol core: SSE 6 events, `Component`/`ComponentSchema` envelope, `ComponentAdapter` Protocol, verb catalogue, auth seam, testing DSL | M1 ✅ |
| `agentkit-runtime` | `LanggraphOrchestrator` (Orchestrator Protocol impl): `create_agent` + `build_adapter_tools` + `build_frontend_tools` + `interrupt()` HITL | M2 ✅ (0.3.0 repositioned) |

### Development

```bash
uvx --from rust-just just init      # sync deps + install pre-commit hooks
uvx --from rust-just just lint      # ruff check --fix + format
uvx --from rust-just just test      # pytest (dev Python version)
uvx --from rust-just just test-all  # pytest across the configured Python range
```

### Examples

`example/` holds two runnable demos (`OPENROUTER_API_KEY` required):

```bash
export OPENROUTER_API_KEY="sk-or-v1-..."
uv run --with fastapi --with uvicorn --with langchain-openai python example/fastapi-bi/backend.py
uv run --with pyside6 --with qasync --with langchain-openai python example/pyside-dcc/app.py
```

See [`example/README.md`](example/README.md) for details.
