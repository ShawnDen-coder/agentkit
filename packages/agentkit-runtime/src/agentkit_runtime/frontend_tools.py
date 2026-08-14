"""frontend_tools: 4 frozen frontend verbs + runtime-extension verbs as langchain tools.

The 4 frozen frontend verbs (``add_component_to_dashboard``,
``update_component_in_dashboard``, ``manage_navigation_bar``,
``assign_tasks_to_agents``) are in core's frozen catalogue (narrow waist ②: the
FunctionCall round-trip contract). Runtime may add extension frontend verbs
(like ``connect_nodes`` for the node-editor example) without bumping
``PROTOCOL_VERSION`` — they live in runtime, not core.

A frontend-verb tool calls langgraph ``interrupt(args)``, which pauses the graph
(raises ``GraphInterrupt`` inside the tool). The orchestrator's ``run()`` catches
this via ``on_tool_error`` in ``astream_events(version="v2")``, yields a
``CopilotFunctionCall`` SSE, and ends the stream. The frontend executes the UI
action and re-POSTs with ``thread_id`` + ``resume`` to continue.

This is the stateless equivalent of langgraph ``interrupt()`` — no
``FrontendActionRequested`` exception, no custom HITL mechanism. Just langgraph's
native HITL primitive.
"""

from __future__ import annotations

from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel
from pydantic import Field


__all__ = ["build_frontend_tools"]


class _AddComponentArgs(BaseModel):
    """Args for add_component_to_dashboard."""

    component_id: str = Field(..., description="The component to add to the dashboard")


class _UpdateComponentArgs(BaseModel):
    """Args for update_component_in_dashboard."""

    component_id: str = Field(..., description="The component to update")
    changes: dict[str, Any] = Field(default_factory=dict, description="Changes to apply")


class _ManageNavBarArgs(BaseModel):
    """Args for manage_navigation_bar."""

    action: str = Field(..., description="Navigation bar action to perform")


class _AssignTasksArgs(BaseModel):
    """Args for assign_tasks_to_agents."""

    tasks: list[Any] = Field(..., description="Tasks to assign to agents")


class _ConnectNodesArgs(BaseModel):
    """Args for connect_nodes (runtime-extension frontend verb, not in core)."""

    source_node: str = Field(..., description="Source node name")
    source_port: int = Field(0, description="Source node output port index")
    target_node: str = Field(..., description="Target node name")
    target_port: int = Field(0, description="Target node input port index")


def build_frontend_tools() -> list[BaseTool]:
    """Build the 4 frozen frontend-verb tools + runtime-extension verbs.

    The 4 frozen verbs are in core's catalogue (narrow waist ②). The runtime
    may add extension frontend verbs (like ``connect_nodes``) without bumping
    ``PROTOCOL_VERSION`` — they live here, not in core.

    Each tool calls ``interrupt(args)`` which pauses the graph. The orchestrator
    catches the resulting ``GraphInterrupt`` (surfaced as ``on_tool_error`` in
    ``astream_events`` v2) and yields a ``CopilotFunctionCall`` SSE event.

    Returns:
        5 langchain ``BaseTool`` objects (4 frozen + 1 runtime extension).
    """

    async def _add_component_to_dashboard(config: RunnableConfig, component_id: str) -> dict[str, Any]:
        """Add a component to the dashboard (frontend UI action)."""
        return interrupt({"component_id": component_id})

    async def _update_component_in_dashboard(
        config: RunnableConfig, component_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing dashboard component (frontend UI action)."""
        return interrupt({"component_id": component_id, "changes": changes})

    async def _manage_navigation_bar(config: RunnableConfig, action: str) -> dict[str, Any]:
        """Modify the host navigation bar (frontend UI action)."""
        return interrupt({"action": action})

    async def _assign_tasks_to_agents(config: RunnableConfig, tasks: list[Any]) -> dict[str, Any]:
        """Assign tasks to other agents (frontend UI action)."""
        return interrupt({"tasks": tasks})

    async def _connect_nodes(
        config: RunnableConfig,
        source_node: str,
        target_node: str,
        source_port: int = 0,
        target_port: int = 0,
    ) -> dict[str, Any]:
        """Connect two nodes' ports (frontend UI action, runtime extension)."""
        return interrupt({
            "source_node": source_node,
            "source_port": source_port,
            "target_node": target_node,
            "target_port": target_port,
        })

    return [
        StructuredTool.from_function(
            None,
            coroutine=_add_component_to_dashboard,
            name="add_component_to_dashboard",
            description="Add a component to the dashboard (frontend UI action).",
            args_schema=_AddComponentArgs,
        ),
        StructuredTool.from_function(
            None,
            coroutine=_update_component_in_dashboard,
            name="update_component_in_dashboard",
            description="Update an existing dashboard component (frontend UI action).",
            args_schema=_UpdateComponentArgs,
        ),
        StructuredTool.from_function(
            None,
            coroutine=_manage_navigation_bar,
            name="manage_navigation_bar",
            description="Modify the host navigation bar (frontend UI action).",
            args_schema=_ManageNavBarArgs,
        ),
        StructuredTool.from_function(
            None,
            coroutine=_assign_tasks_to_agents,
            name="assign_tasks_to_agents",
            description="Assign tasks to other agents (frontend UI action).",
            args_schema=_AssignTasksArgs,
        ),
        StructuredTool.from_function(
            None,
            coroutine=_connect_nodes,
            name="connect_nodes",
            description="Connect two nodes' ports (frontend UI action, runtime extension).",
            args_schema=_ConnectNodesArgs,
        ),
    ]
