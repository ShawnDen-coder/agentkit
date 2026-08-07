"""Standard verb catalogue (Option B: backend sync vs frontend FunctionCall).

A Verb is a named action the LLM may request. Per Option B (§4.2.2 / §D.4), verbs
split by execution location:
  * backend  - orchestrator executes synchronously (adapter method / skill registry /
               MCP gateway); result returns to the LLM within the same request (multi-hop).
  * frontend - orchestrator yields a FunctionCallSSE; the frontend executes and re-POSTs
               a role=tool result. Reserved for UI actions only.

M1 freezes the verb *catalogue* (names + input schemas + category). The live
VerbRegistry (binding handlers) is wired in M2 (agentkit-runtime).
"""

from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field as PydanticField


__all__ = ["BACKEND_VERBS", "FRONTEND_VERBS", "STANDARD_VERBS", "VerbCategory", "VerbSpec"]

VerbCategory = Literal["backend", "frontend"]


class VerbSpec(BaseModel):
    """Declarative verb definition: name, category, and JSON-schema input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    executes_on: VerbCategory
    input_schema: dict[str, Any] = PydanticField(
        default_factory=dict,
        description="JSON Schema for the verb's arguments (langchain tool input_schema).",
    )


BACKEND_VERBS: list[VerbSpec] = [
    VerbSpec(
        name="get_component_data",
        description="Fetch data for a component (adapter method).",
        executes_on="backend",
        input_schema={
            "type": "object",
            "properties": {
                "component_id": {"type": "string"},
                "input_args": {"type": "object"},
            },
            "required": ["component_id"],
        },
    ),
    VerbSpec(
        name="refine_component",
        description="Refine an already-fetched component (filter/drill/swap measure) via its semantic model.",
        executes_on="backend",
        input_schema={
            "type": "object",
            "properties": {
                "component_id": {"type": "string"},
                "refinement": {"type": "object"},
            },
            "required": ["component_id", "refinement"],
        },
    ),
    VerbSpec(
        name="get_catalog",
        description="List available components/datasets (adapter method).",
        executes_on="backend",
        input_schema={"type": "object", "properties": {}},
    ),
    VerbSpec(
        name="get_selection",
        description="Return the user's current selection in the host tool (adapter method).",
        executes_on="backend",
        input_schema={"type": "object", "properties": {}},
    ),
    VerbSpec(
        name="get_semantic_model",
        description="Fetch the semantic model (schema) of a component (adapter method).",
        executes_on="backend",
        input_schema={
            "type": "object",
            "properties": {"component_id": {"type": "string"}},
            "required": ["component_id"],
        },
    ),
    VerbSpec(
        name="get_skill_content",
        description="Fetch a loaded skill's prompt content (skill registry).",
        executes_on="backend",
        input_schema={
            "type": "object",
            "properties": {"skill": {"type": "string"}},
            "required": ["skill"],
        },
    ),
    VerbSpec(
        name="execute_tool",
        description="Execute an MCP tool via the framework gateway (M6).",
        executes_on="backend",
        input_schema={
            "type": "object",
            "properties": {
                "tool": {"type": "string"},
                "arguments": {"type": "object"},
            },
            "required": ["tool"],
        },
    ),
]

FRONTEND_VERBS: list[VerbSpec] = [
    VerbSpec(
        name="add_component_to_dashboard",
        description="Add a component to the dashboard (frontend UI action).",
        executes_on="frontend",
        input_schema={
            "type": "object",
            "properties": {"component_id": {"type": "string"}},
            "required": ["component_id"],
        },
    ),
    VerbSpec(
        name="update_component_in_dashboard",
        description="Update an existing dashboard component (frontend UI action).",
        executes_on="frontend",
        input_schema={
            "type": "object",
            "properties": {
                "component_id": {"type": "string"},
                "changes": {"type": "object"},
            },
            "required": ["component_id"],
        },
    ),
    VerbSpec(
        name="manage_navigation_bar",
        description="Modify the host navigation bar (frontend UI action).",
        executes_on="frontend",
        input_schema={"type": "object", "properties": {"action": {"type": "string"}}},
    ),
    VerbSpec(
        name="assign_tasks_to_agents",
        description="Assign tasks to other agents (frontend UI action).",
        executes_on="frontend",
        input_schema={"type": "object", "properties": {"tasks": {"type": "array"}}},
    ),
]

STANDARD_VERBS: list[VerbSpec] = [*BACKEND_VERBS, *FRONTEND_VERBS]
