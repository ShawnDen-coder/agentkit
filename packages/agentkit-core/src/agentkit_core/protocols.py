"""Protocols (structural contracts) for the adapter, orchestrator, and LLM client.

These are the abstract seams of the framework. M1 freezes the *Protocol* shapes;
concrete implementations arrive in later milestones:
  - ComponentAdapter impls: BI adapters (M3), DCC adapters (M8+), MockAdapter (M2).
  - Orchestrator impl: StatelessOrchestrator (M2, agentkit-runtime).
  - LlmClient impl: LangChainLlmClient (M2, agentkit-llm-langchain).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from agentkit_core.llm import LlmChunk
from agentkit_core.llm import LlmResponse
from agentkit_core.llm import ToolDef
from agentkit_core.models import AdapterCapabilities
from agentkit_core.models import BaseSSE
from agentkit_core.models import Component
from agentkit_core.models import ComponentData
from agentkit_core.models import ComponentSchema
from agentkit_core.models import QueryRequest
from agentkit_core.models import Refinement
from agentkit_core.models import SessionContext


__all__ = ["ComponentAdapter", "LlmClient", "Orchestrator", "VerbHandler"]


@runtime_checkable
class ComponentAdapter(Protocol):
    """Narrow waist ①: translates a host tool's native objects into agentkit Components.

    Implementations live in adapter packages (agentkit-adapter-superset, ...). A
    runtime discovers adapters via the ``agentkit.adapters`` entry-point group and
    never statically depends on them (§C.1). ``origin`` + ``capabilities`` are
    instance attributes; the methods map 1:1 to the backend-sync verbs (§D.4).
    """

    origin: str  # "superset" | "metabase" | "maya" | ...
    capabilities: AdapterCapabilities

    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """Return the catalog of available components (verb: get_catalog)."""
        ...

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Return a single component by id."""
        ...

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, Any]
    ) -> ComponentData:
        """Fetch data for a component (verb: get_component_data). RLS via ctx."""
        ...

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData:
        """Refine an already-fetched component via its semantic model (verb: refine_component)."""
        ...

    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema:
        """Fetch the semantic model (schema) of a component (verb: get_semantic_model)."""
        ...


@runtime_checkable
class Orchestrator(Protocol):
    """Runs a query and yields the SSE stream. Stateless: state lives in request.messages.

    ``run`` is an async generator: calling it returns an ``AsyncIterator[BaseSSE]``
    (not a coroutine). The M2 impl (StatelessOrchestrator) follows the Option B core
    loop (§6.1): backend-sync fetch within the request, streaming chunks/artifacts.
    """

    def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine)."""
        ...


@runtime_checkable
class LlmClient(Protocol):
    """LLM call layer. Providers swap via env; agent code is provider-agnostic (§6.4).

    Two methods map to the Option B two-phase loop:
      - ``call`` (Phase 1, non-streaming, with tools): returns a ``LlmResponse`` whose
        ``tool_calls`` the orchestrator routes (backend sync vs frontend FunctionCall).
      - ``stream`` (Phase 2, streaming, usually without tools): yields ``LlmChunk``
        text deltas for the final answer.

    The M2 default impl (agentkit-llm-langchain) wraps a langchain ChatModel and
    converts between these provider-neutral types and langchain's own.
    """

    def stream(
        self,
        messages: list[Any],
        tools: list[ToolDef] | None = None,
    ) -> AsyncIterator[LlmChunk]:
        """Yield streamed text chunks (async generator). Phase 2 final answer."""
        ...

    async def call(
        self,
        messages: list[Any],
        tools: list[ToolDef] | None = None,
    ) -> LlmResponse:
        """Return a full response (Phase 1: with tools to obtain tool_calls)."""
        ...


# A verb handler is an async callable: (session context, verb arguments) -> result dict.
VerbHandler = Callable[[SessionContext, dict[str, Any]], Awaitable[dict[str, Any]]]
