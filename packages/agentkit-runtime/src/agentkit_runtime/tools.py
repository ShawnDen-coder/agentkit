"""Tool schemas + handlers binding the 11 ``STANDARD_VERBS`` to adapter methods.

Per Option B (§D.4), the LLM sees all 11 verbs as langchain tools (it does not know
which are backend vs. frontend). The orchestrator routes: backend verbs execute
synchronously via the adapter; frontend verbs raise ``FrontendActionRequested`` so the
orchestrator's ``run()`` can yield a ``CopilotFunctionCall`` and end the stream.

``VerbSpec.input_schema`` is already JSON Schema — ``bind_tools`` accepts the raw
OpenAI function-calling dict format directly, so no pydantic ``args_schema`` conversion
is needed.
"""

from __future__ import annotations

from typing import Any

from agentkit_protocol import STANDARD_VERBS
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext
from agentkit_protocol.protocols import VerbHandler


__all__ = ["FRONTEND_VERB_NAMES", "FrontendActionRequested", "build_tool_handlers", "verb_tool_schemas"]


# Verb names that execute on the frontend (yield CopilotFunctionCall, end stream).
FRONTEND_VERB_NAMES: set[str] = {v.name for v in STANDARD_VERBS if v.executes_on == "frontend"}


class FrontendActionRequested(Exception):
    """Raised by a frontend-verb handler to break out of the langgraph loop.

    Carries the verb name + arguments so ``LanggraphOrchestrator.run`` can yield a
    ``CopilotFunctionCall`` SSE event and end the stream. The frontend executes the UI
    action and re-POSTs with ``role=tool`` to resume.
    """

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        """Store the verb name + arguments for the outer ``run()`` to yield."""
        super().__init__(name)
        self.name = name
        self.arguments = arguments


def verb_tool_schemas() -> list[dict[str, Any]]:
    """Build the OpenAI function-calling tool dict list for ``bind_tools``.

    Each ``VerbSpec`` is already JSON-Schema-shaped, so this is a 1:1 mapping — no
    pydantic ``args_schema`` conversion.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": v.name,
                "description": v.description,
                "parameters": v.input_schema,
            },
        }
        for v in STANDARD_VERBS
    ]


def build_tool_handlers(adapter: ComponentAdapter) -> dict[str, VerbHandler]:
    """Bind each verb name to an async handler that calls the adapter.

    Backend verbs (7) call the matching ``ComponentAdapter`` method. The 2 unimplemented
    backend verbs (``get_skill_content``, ``execute_tool``) raise ``NotImplementedError``
    so the ``tools_node`` can turn them into a ``ToolMessage`` for LLM recovery.
    Frontend verbs (4) raise ``FrontendActionRequested`` to end the stream.
    """

    async def _get_catalog(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        components = await adapter.list_components(ctx)
        return {"components": [c.model_dump(by_alias=True) for c in components]}

    async def _get_selection(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        data = await adapter.get_selection(ctx)
        return data.model_dump()

    async def _get_component_data(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        component_id = args["component_id"]
        input_args = args.get("input_args", {})
        component = await adapter.get_component(ctx, component_id)
        data = await adapter.get_component_data(ctx, component, input_args)
        return data.model_dump()

    async def _get_semantic_model(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        component_id = args["component_id"]
        component = await adapter.get_component(ctx, component_id)
        schema = await adapter.get_semantic_model(ctx, component)
        return schema.model_dump()

    async def _refine_component(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        component_id = args["component_id"]
        refinement_args = args.get("refinement", {})
        component = await adapter.get_component(ctx, component_id)
        extra = {k: v for k, v in refinement_args.items() if k != "kind"}
        refinement = Refinement(kind=refinement_args.get("kind", "generic"), **extra)
        data = await adapter.refine_component(ctx, component, refinement)
        return data.model_dump()

    async def _get_skill_content(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("skill registry is M4")

    async def _execute_tool(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("MCP gateway is M6")

    def _frontend(name: str) -> VerbHandler:
        async def _raise(ctx: SessionContext, args: dict[str, Any]) -> dict[str, Any]:
            raise FrontendActionRequested(name, args)

        return _raise

    handlers: dict[str, VerbHandler] = {
        "get_catalog": _get_catalog,
        "get_selection": _get_selection,
        "get_component_data": _get_component_data,
        "get_semantic_model": _get_semantic_model,
        "refine_component": _refine_component,
        "get_skill_content": _get_skill_content,
        "execute_tool": _execute_tool,
    }
    for name in FRONTEND_VERB_NAMES:
        handlers[name] = _frontend(name)
    return handlers
