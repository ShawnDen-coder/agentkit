# AgentKit

### Overview

A transferable, embeddable agent framework for data-driven tools (BI dashboards now;
DCC hosts like Maya/UE/PySide later). Modeled on OpenBB Workspace: two narrow waists
(a frozen `ComponentAdapter` contract + a frozen SSE protocol) carry the portability;
domain semantics live in swappable profile packages (`agentkit-bi`, future `agentkit-dcc`).

- **Core is domain-neutral** (only `pydantic`); **langchain** enters only at the
  `LlmClient` layer (M2), never the contracts.
- **Orchestration is stateless** (hand-rolled; state lives in `request.messages`).
- **Option B**: data/skill/MCP are backend-sync calls; the FunctionCall loop is reserved
  for frontend UI actions only.

See [`agentkit-architecture.md`](../agentkit-architecture.md) for the full design and
[`docs/contracts.md`](docs/contracts.md) for the M1 frozen-contract surface.

### Workspace layout

uv workspace; packages live under `packages/`.

| Package | Description | Milestone |
|---------|-------------|-----------|
| `agentkit-core` | Domain-neutral protocol core: SSE 6 events, `Component`/`ComponentSchema` envelope, `ComponentAdapter` Protocol, verb catalogue, testing DSL | M1 ✅ |
| `agentkit-bi` | BI profile: `BiSemanticModel`, `Widget`, `WidgetData`, `ChartArtifact`, `BiAdapter` base, BI prompt builder | M1 ✅ |

### Development

```bash
uvx --from rust-just just init      # sync deps + install pre-commit hooks
uvx --from rust-just just lint      # ruff check --fix + format
uvx --from rust-just just test      # pytest (dev Python version)
uvx --from rust-just just test-all  # pytest across the configured Python range
```
