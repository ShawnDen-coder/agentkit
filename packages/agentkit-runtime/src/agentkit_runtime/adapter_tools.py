"""adapter_tools: bind a ComponentAdapter's data methods to langchain tools.

The 7 backend verbs are NOT frozen in core (0.3.0) - they live here as langchain
tools, schema derived from pydantic ``args_schema`` models. The adapter's data
contract (``ComponentAdapter`` Protocol) is frozen (narrow waist ①); tool
exposure is langchain-native and not frozen.

Each tool:
  * emits a ``status`` side-channel event via ``adispatch_custom_event``
  * calls the matching ``ComponentAdapter`` method
  * if a ``to_artifact`` profile hook is provided and returns one, emits an
    ``artifact`` side-channel event
  * returns the result as JSON

The 2 unimplemented backend verbs (``get_skill_content``, ``execute_tool``) are
NOT exposed here - they raise ``NotImplementedError`` until M4/M6 land. Exposing
them would let the LLM call known-unavailable tools and burn token/hop budget.

Streaming: ``adispatch_custom_event`` (config-explicit, 3.10-safe) consumed via
``astream_events(version="v2")`` ``on_custom_event``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.tools import StructuredTool
from pydantic import BaseModel
from pydantic import Field

from agentkit_protocol import Artifact
from agentkit_protocol import Authorizer
from agentkit_protocol import AuthzAction
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import Principal
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext


__all__ = ["ToArtifact", "build_adapter_tools"]


# Profile-injected hook: turn a ComponentData dump into an Artifact (or None).
# agentkit-bi provides to_table_artifact; future agentkit-dcc provides its own.
# None means "this data has no artifact form" - runtime does NOT guess.
ToArtifact = Callable[[dict[str, Any]], "Artifact | None"]


# ---------------------------------------------------------------------------
# Per-verb args_schema (langchain tool input schema, NOT frozen in core)
# ---------------------------------------------------------------------------


class _GetCatalogArgs(BaseModel):
    """Args for get_catalog (empty - lists all components)."""


class _GetComponentDataArgs(BaseModel):
    """Args for get_component_data."""

    component_id: str = Field(..., description="The component to fetch data for")
    input_args: dict[str, Any] = Field(default_factory=dict, description="Filter/sort/params for the fetch")


class _GetSelectionArgs(BaseModel):
    """Args for get_selection (empty - returns current user selection)."""


class _GetSemanticModelArgs(BaseModel):
    """Args for get_semantic_model."""

    component_id: str = Field(..., description="The component whose semantic model to fetch")


class _RefineComponentArgs(BaseModel):
    """Args for refine_component."""

    component_id: str = Field(..., description="The component to refine")
    refinement: dict[str, Any] = Field(..., description="Refinement spec (filter/drill/measure swap)")


# ---------------------------------------------------------------------------
# Status labels (per-verb, Chinese for consistency with examples)
# ---------------------------------------------------------------------------


_VERB_STATUS_LABELS: dict[str, str] = {
    "get_catalog": "正在获取目录",
    "get_component_data": "正在获取数据",
    "get_selection": "正在获取选择",
    "get_semantic_model": "正在获取语义模型",
    "refine_component": "正在精炼组件",
}


# ---------------------------------------------------------------------------
# Helper: emit artifact if the profile hook returns one
# ---------------------------------------------------------------------------


async def _maybe_emit_artifact(
    result: dict[str, Any],
    to_artifact: ToArtifact | None,
    config: RunnableConfig,
) -> None:
    """If a profile ``to_artifact`` hook is provided and returns one, emit it.

    Runtime does NOT sniff ``ComponentData`` shape (the M2 ``_maybe_artifact``
    BI-specific ``columns``/``rows`` check is removed). Profile code declares
    how its data becomes an artifact; core stays domain-neutral.
    """
    if to_artifact is None:
        return
    artifact = to_artifact(result)
    if artifact is not None:
        await adispatch_custom_event("artifact", {"artifact": artifact}, config=config)


async def _emit_status(verb: str, config: RunnableConfig) -> None:
    """Emit a 'running' status event with the verb's label."""
    label = _VERB_STATUS_LABELS.get(verb, verb)
    await adispatch_custom_event("status", {"status": "running", "label": label}, config=config)


async def _authorize(
    authorizer: Authorizer | None,
    config: RunnableConfig,
    verb: str,
    component_id: str | None = None,
    args: dict[str, Any] | None = None,
) -> None:
    """Per-verb RLS check. If authorizer is None, skip (dev/test mode).

    Reads the Principal from config["configurable"]["principal"] (set by the
    orchestrator from the authenticated request). Raises AuthorizationError on
    denial (the orchestrator's ToolErrorMiddleware converts it to a ToolMessage
    for LLM recovery, or the app layer maps it to HTTP 403).
    """
    if authorizer is None:
        return
    principal: Principal = config["configurable"]["principal"]
    await authorizer.authorize(
        principal,
        AuthzAction(verb=verb, component_id=component_id, args=args or {}),
    )


# ---------------------------------------------------------------------------
# Tool builders (one per backend verb)
# ---------------------------------------------------------------------------


def _build_get_catalog(
    adapter: ComponentAdapter, to_artifact: ToArtifact | None, authorizer: Authorizer | None
) -> BaseTool:
    """Build the get_catalog tool (lists available components)."""

    async def _run(config: RunnableConfig) -> str:
        ctx: SessionContext = config["configurable"]["ctx"]
        await _authorize(authorizer, config, verb="get_catalog")
        await _emit_status("get_catalog", config)
        components = await adapter.list_components(ctx)
        result: dict[str, Any] = {"components": [c.model_dump(by_alias=True) for c in components]}
        await _maybe_emit_artifact(result, to_artifact, config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name="get_catalog",
        description="List available components/datasets (adapter method).",
        args_schema=_GetCatalogArgs,
    )


def _build_get_component_data(
    adapter: ComponentAdapter, to_artifact: ToArtifact | None, authorizer: Authorizer | None
) -> BaseTool:
    """Build the get_component_data tool (fetches data for a component)."""

    async def _run(config: RunnableConfig, component_id: str, input_args: dict[str, Any] | None = None) -> str:
        ctx: SessionContext = config["configurable"]["ctx"]
        await _authorize(authorizer, config, verb="get_component_data", component_id=component_id, args=input_args)
        await _emit_status("get_component_data", config)
        component = await adapter.get_component(ctx, component_id)
        data = await adapter.get_component_data(ctx, component, input_args or {})
        result = data.model_dump()
        await _maybe_emit_artifact(result, to_artifact, config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name="get_component_data",
        description="Fetch data for a component (adapter method).",
        args_schema=_GetComponentDataArgs,
    )


def _build_get_selection(
    adapter: ComponentAdapter, to_artifact: ToArtifact | None, authorizer: Authorizer | None
) -> BaseTool:
    """Build the get_selection tool (returns user's current selection)."""

    async def _run(config: RunnableConfig) -> str:
        ctx: SessionContext = config["configurable"]["ctx"]
        await _authorize(authorizer, config, verb="get_selection")
        await _emit_status("get_selection", config)
        data = await adapter.get_selection(ctx)
        result = data.model_dump()
        await _maybe_emit_artifact(result, to_artifact, config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name="get_selection",
        description="Return the user's current selection in the host tool (adapter method).",
        args_schema=_GetSelectionArgs,
    )


def _build_get_semantic_model(
    adapter: ComponentAdapter, to_artifact: ToArtifact | None, authorizer: Authorizer | None
) -> BaseTool:
    """Build the get_semantic_model tool (fetches a component's schema)."""

    async def _run(config: RunnableConfig, component_id: str) -> str:
        ctx: SessionContext = config["configurable"]["ctx"]
        await _authorize(authorizer, config, verb="get_semantic_model", component_id=component_id)
        await _emit_status("get_semantic_model", config)
        component = await adapter.get_component(ctx, component_id)
        schema = await adapter.get_semantic_model(ctx, component)
        result = schema.model_dump()
        await _maybe_emit_artifact(result, to_artifact, config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name="get_semantic_model",
        description="Fetch the semantic model (schema) of a component (adapter method).",
        args_schema=_GetSemanticModelArgs,
    )


def _build_refine_component(
    adapter: ComponentAdapter, to_artifact: ToArtifact | None, authorizer: Authorizer | None
) -> BaseTool:
    """Build the refine_component tool (filters/drills/swaps measure on fetched data)."""

    async def _run(config: RunnableConfig, component_id: str, refinement: dict[str, Any]) -> str:
        ctx: SessionContext = config["configurable"]["ctx"]
        await _authorize(authorizer, config, verb="refine_component", component_id=component_id, args=refinement)
        await _emit_status("refine_component", config)
        component = await adapter.get_component(ctx, component_id)
        # Refinement is a polymorphic envelope (kind + extra="allow"); rebuild from dict.
        extra = {k: v for k, v in refinement.items() if k != "kind"}
        refinement_obj = Refinement(kind=refinement.get("kind", "generic"), **extra)
        data = await adapter.refine_component(ctx, component, refinement_obj)
        result = data.model_dump()
        await _maybe_emit_artifact(result, to_artifact, config)
        return json.dumps(result)

    return StructuredTool.from_function(
        None,
        coroutine=_run,
        name="refine_component",
        description="Refine an already-fetched component via its semantic model (adapter method).",
        args_schema=_RefineComponentArgs,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_adapter_tools(
    adapter: ComponentAdapter,
    *,
    to_artifact: ToArtifact | None = None,
    authorizer: Authorizer | None = None,
) -> list[BaseTool]:
    """Build langchain tools for the 5 implemented backend verbs.

    Each tool: (1) checks per-verb authorization if an ``authorizer`` is provided,
    (2) emits a ``status`` side-channel event, (3) calls the matching
    ``ComponentAdapter`` method, (4) optionally emits an ``artifact`` event via the
    profile-injected ``to_artifact`` hook, and (5) returns the result as JSON.

    The 2 stub verbs (``get_skill_content``, ``execute_tool``) are NOT included
    here - they raise ``NotImplementedError`` until M4 (skills) / M6 (MCP) land.
    Exposing them would let the LLM call known-unavailable tools.

    Args:
        adapter: The ComponentAdapter whose methods back the tools.
        to_artifact: Optional profile hook (e.g. BI's ``to_table_artifact``)
            that converts a ``ComponentData`` dump into an ``Artifact``. If
            None, no artifact events are emitted. Runtime does NOT sniff data
            shape - the profile declares the mapping.
        authorizer: Optional ``Authorizer`` for per-verb RLS. If provided, each
            tool calls ``authorizer.authorize(principal, AuthzAction(verb, ...))``
            before the adapter method. The ``Principal`` is read from
            ``config["configurable"]["principal"]`` (set by the orchestrator from
            the authenticated request). If None, authorization is skipped (dev/test).

    Returns:
        5 langchain ``BaseTool`` objects (one per implemented backend verb).
    """
    return [
        _build_get_catalog(adapter, to_artifact, authorizer),
        _build_get_component_data(adapter, to_artifact, authorizer),
        _build_get_selection(adapter, to_artifact, authorizer),
        _build_get_semantic_model(adapter, to_artifact, authorizer),
        _build_refine_component(adapter, to_artifact, authorizer),
    ]
