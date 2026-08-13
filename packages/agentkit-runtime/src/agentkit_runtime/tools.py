"""Verb tools: bind the 11 ``STANDARD_VERBS`` to langchain ``BaseTool`` objects.

Per Option B (§D.4), the LLM sees all 11 verbs as langchain tools (it does not know
which are backend vs. frontend). ``create_agent`` (langchain v1) drives the agent↔tools
loop; each verb is a ``StructuredTool`` whose coroutine:

  * **frontend verb** -> raises ``FrontendActionRequested`` so the orchestrator's
    ``run()`` can yield a ``CopilotFunctionCall`` and end the stream (Option B
    frontend round-trip). This is the stateless equivalent of langgraph ``interrupt()``
    (which would require a checkpointer, breaking the frozen stateless contract).
  * **backend verb** -> calls the matching ``ComponentAdapter`` method, emits
    ``status``/``artifact`` side-channel events via ``adispatch_custom_event``, and
    returns the result as JSON.

``ToolErrorMiddleware`` (wired in the orchestrator) turns ``NotImplementedError`` (the
skill/MCP stubs) into an error ``ToolMessage`` for LLM recovery and lets
``FrontendActionRequested`` propagate.

LLM-facing schema: each tool's ``args_schema`` is a pydantic model built from the frozen
``VerbSpec.input_schema``. The derived OpenAI schema is functionally equivalent (required
fields/types match); optional fields carry an additive ``default: null`` and object/array
fields carry ``additionalProperties``/``items`` (pydantic defaults). The frozen
``VerbSpec.input_schema`` in the protocol package remains the authoritative source.

Streaming note: we emit via ``adispatch_custom_event`` (config-explicit, 3.10-safe) and
consume via ``astream_events(version="v2")`` ``on_custom_event``. ``get_stream_writer`` /
``stream_mode="custom"`` is 3.11+-async-only (contextvar) and cannot be used - the project
supports Python 3.10.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from pydantic import create_model

from agentkit_protocol import STANDARD_VERBS
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext
from agentkit_protocol import TableArtifact
from agentkit_protocol import VerbSpec
from agentkit_protocol.protocols import VerbHandler


__all__ = [
    "FRONTEND_VERB_NAMES",
    "VERB_STATUS_LABELS",
    "FrontendActionRequested",
    "verb_tools",
]


# Verb names that execute on the frontend (yield CopilotFunctionCall, end stream).
FRONTEND_VERB_NAMES: set[str] = {v.name for v in STANDARD_VERBS if v.executes_on == "frontend"}


# Chinese status labels per verb (consistency with FakeOrchestrator).
VERB_STATUS_LABELS: dict[str, str] = {
    "get_catalog": "正在获取目录",
    "get_component_data": "正在获取数据",
    "get_selection": "正在获取选择",
    "get_semantic_model": "正在获取语义模型",
    "refine_component": "正在精炼组件",
    "get_skill_content": "正在获取技能内容",
    "execute_tool": "正在执行工具",
}


class FrontendActionRequested(Exception):
    """Raised by a frontend-verb tool to break out of the ``create_agent`` loop.

    Carries the verb name + arguments so ``LanggraphOrchestrator.run`` can yield a
    ``CopilotFunctionCall`` SSE event and end the stream. The frontend executes the UI
    action and re-POSTs with ``role=tool`` to resume. This is the stateless equivalent
    of langgraph ``interrupt()`` (which requires a checkpointer).
    """

    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        """Store the verb name + arguments for the outer ``run()`` to yield."""
        super().__init__(name)
        self.name = name
        self.arguments = arguments


def _backend_handlers(adapter: ComponentAdapter) -> dict[str, VerbHandler]:
    """Bind each backend verb name to an async handler that calls the adapter.

    Backend verbs (7) call the matching ``ComponentAdapter`` method. The 2 unimplemented
    backend verbs (``get_skill_content``, ``execute_tool``) raise ``NotImplementedError``
    so ``ToolErrorMiddleware`` can turn them into a ``ToolMessage`` for LLM recovery.
    Frontend verbs (4) are NOT here - their tool coroutine raises
    ``FrontendActionRequested`` directly.
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

    return {
        "get_catalog": _get_catalog,
        "get_selection": _get_selection,
        "get_component_data": _get_component_data,
        "get_semantic_model": _get_semantic_model,
        "refine_component": _refine_component,
        "get_skill_content": _get_skill_content,
        "execute_tool": _execute_tool,
    }


def _maybe_artifact(result: dict[str, Any]) -> Any:
    """Peek at a handler result dict; if it looks like tabular ComponentData, build an Artifact.

    Handlers return ``model_dump()`` dicts. A ``ComponentData`` dump carries ``kind`` +
    (for BI tables) ``columns``/``rows``. Matches ``FakeOrchestrator._to_artifact``.
    """
    kind = result.get("kind")
    if kind is None:
        return None
    if "columns" in result and "rows" in result:
        return TableArtifact(
            columns=list(result["columns"]),
            rows=[list(r) for r in result["rows"]],
        )
    return None


_JSON_TYPE_TO_PY: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}


def _args_schema_for(spec: VerbSpec) -> type[BaseModel]:
    """Build a pydantic ``args_schema`` from the frozen ``VerbSpec.input_schema``.

    Flat JSON Schemas only (the standard verbs are flat). Required fields become required
    pydantic fields; optional fields get ``default=None``. The derived OpenAI schema is
    functionally equivalent to ``spec.input_schema`` (see module docstring).
    """
    props = spec.input_schema.get("properties", {})
    required = set(spec.input_schema.get("required", []))
    fields: dict[str, Any] = {}
    for name, js in props.items():
        py_type = _JSON_TYPE_TO_PY.get(js.get("type", ""), Any)
        fields[name] = (py_type, ...) if name in required else (py_type, None)
    return create_model(f"{spec.name}_args", **fields) if fields else create_model(f"{spec.name}_args")


def _make_verb_tool(spec: VerbSpec, handler: VerbHandler | None) -> BaseTool:
    """Build a ``StructuredTool`` for one verb.

    Frontend verbs (``handler is None``) raise ``FrontendActionRequested``. Backend verbs
    emit a ``status`` event, call the handler (which may raise ``NotImplementedError`` ->
    ``ToolErrorMiddleware`` -> ``ToolMessage``), emit an ``artifact`` event if the result
    looks tabular, and return the result as JSON.
    """

    async def _run(config: RunnableConfig, **args: Any) -> str:
        if spec.executes_on == "frontend":
            raise FrontendActionRequested(spec.name, args)
        assert handler is not None  # backend verbs always have a handler
        ctx: SessionContext = config["configurable"]["ctx"]
        label = VERB_STATUS_LABELS.get(spec.name, spec.name)
        await adispatch_custom_event("status", {"status": "running", "label": label}, config=config)
        result = await handler(ctx, args)
        artifact = _maybe_artifact(result)
        if artifact is not None:
            await adispatch_custom_event("artifact", {"artifact": artifact}, config=config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name=spec.name,
        description=spec.description,
        args_schema=_args_schema_for(spec),
    )


def verb_tools(adapter: ComponentAdapter) -> list[BaseTool]:
    """Build the 11 verb tools (one per ``STANDARD_VERBS``) for ``create_agent``."""
    handlers = _backend_handlers(adapter)
    return [_make_verb_tool(spec, handlers.get(spec.name)) for spec in STANDARD_VERBS]
