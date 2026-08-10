"""Protocols (structural contracts) for the adapter and orchestrator.

These are the abstract seams of the framework. M1 freezes the *Protocol* shapes;
concrete implementations arrive in later milestones:
  - ComponentAdapter impls: BI adapters (M3), DCC adapters (M8+), MockAdapter (M2).
  - Orchestrator impl: StatelessOrchestrator (M2, agentkit-runtime).

LLM calls: orchestrator impls use langchain ``BaseChatModel`` directly (no
``LlmClient`` abstraction layer). langchain enters at the runtime package, not
the contracts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from agentkit_protocol.models import AdapterCapabilities
from agentkit_protocol.models import BaseSSE
from agentkit_protocol.models import Component
from agentkit_protocol.models import ComponentData
from agentkit_protocol.models import ComponentSchema
from agentkit_protocol.models import QueryRequest
from agentkit_protocol.models import Refinement
from agentkit_protocol.models import SessionContext


__all__ = ["ComponentAdapter", "Orchestrator", "VerbHandler"]


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

    async def get_selection(self, ctx: SessionContext) -> ComponentData:
        """Return the user's current selection in the host tool (verb: get_selection).

        A polymorphic ``ComponentData`` envelope: BI profiles carry the primary widget
        reference; DCC profiles carry the selected scene nodes/actors/QObjects. RLS via ctx.
        """
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
    LLM calls go through a langchain ``BaseChatModel`` the impl holds directly.
    """

    def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine)."""
        ...


# A verb handler is an async callable: (session context, verb arguments) -> result dict.
VerbHandler = Callable[[SessionContext, dict[str, Any]], Awaitable[dict[str, Any]]]
