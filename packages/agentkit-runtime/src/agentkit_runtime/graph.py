"""The langgraph ``StateGraph`` topology for the Option B core loop.

Two nodes (``agent`` ↔ ``tools``) with a conditional edge after ``agent``:
- If the LLM emitted ``tool_calls`` and ``hops < max_hops`` → run ``tools``.
- Otherwise → END.

The ``tools`` node dispatches each tool call to its handler. Backend-verb handlers
execute synchronously and return a ``ToolMessage``. Frontend-verb handlers raise
``FrontendActionRequested``, which propagates out of ``compiled.astream_events`` so
``LanggraphOrchestrator.run`` can yield a ``CopilotFunctionCall`` and end the stream.

No checkpointer: the orchestrator is stateless (state lives in ``request.messages``).
"""

from __future__ import annotations

import json
from typing import Annotated
from typing import Any
from typing import TypedDict

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage
from langchain_core.messages import BaseMessage
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages

from agentkit_protocol import ComponentAdapter
from agentkit_protocol import SessionContext
from agentkit_protocol import TableArtifact
from agentkit_runtime.tools import FRONTEND_VERB_NAMES
from agentkit_runtime.tools import FrontendActionRequested
from agentkit_runtime.tools import VerbHandler


__all__ = ["VERB_STATUS_LABELS", "GraphState", "build_graph"]


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


class GraphState(TypedDict):
    """Langgraph state: messages (append-only) + hop counter + request-scoped context.

    ``ctx`` is request-scoped (the ``SessionContext``), NOT graph state — but langgraph
    nodes need it, and we have no checkpointer, so stashing it here is simpler than
    threading ``RunnableConfig.configurable``. If a checkpointer is ever added (M3+),
    move ``ctx`` to ``configurable`` (the langgraph-sanctioned channel for request-scoped
    non-state data) — ``SessionContext`` carries a ``SecretStr auth_token`` that should
    not be serialized.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    hops: int
    ctx: SessionContext


def build_graph(
    bound_llm: Any,
    handlers: dict[str, VerbHandler],
    adapter: ComponentAdapter,
    max_hops: int,
) -> Any:
    """Compile the StateGraph. ``bound_llm`` is the LLM with ``bind_tools`` already applied."""
    del adapter  # adapter is captured via handlers; not needed separately here

    async def agent_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
        """Invoke the LLM with the current message history; return its AIMessage."""
        ai_msg = await bound_llm.ainvoke(state["messages"], config=config)
        return {"messages": [ai_msg]}

    async def tools_node(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
        """Dispatch each tool call: backend verbs execute sync, frontend verbs raise."""
        last: AIMessage = state["messages"][-1]
        ctx = state["ctx"]
        tool_calls = getattr(last, "tool_calls", None) or []
        tool_messages: list[ToolMessage] = []
        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})
            tc_id = tc.get("id", f"call_{name}")
            if name in FRONTEND_VERB_NAMES:
                raise FrontendActionRequested(name, args)
            label = VERB_STATUS_LABELS.get(name, name)
            await adispatch_custom_event("status", {"status": "running", "label": label}, config=config)
            handler = handlers[name]
            try:
                result = await handler(ctx, args)
            except NotImplementedError as e:
                tool_messages.append(ToolMessage(content=f"not implemented: {e}", tool_call_id=tc_id))
                continue
            # If the handler returned a ComponentData-bearing result, emit an artifact.
            # (Handlers return dicts; ComponentData round-trips via model_dump. We peek
            # at the dict for the polymorphic artifact rendering — matches FakeOrchestrator.)
            artifact = _maybe_artifact(result)
            if artifact is not None:
                await adispatch_custom_event("artifact", {"artifact": artifact}, config=config)
            tool_messages.append(ToolMessage(content=json.dumps(result), tool_call_id=tc_id))
        return {"messages": tool_messages, "hops": state["hops"] + 1}

    def route_after_agent(state: GraphState) -> str:
        """Continue to ``tools`` if the LLM emitted tool_calls and budget remains."""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None) and state["hops"] < max_hops:
            return "tools"
        return END

    graph = StateGraph(GraphState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


def _maybe_artifact(result: dict[str, Any]) -> Any:
    """Peek at a handler result dict; if it looks like ComponentData, build an Artifact.

    Handlers return ``model_dump()`` dicts. A ``ComponentData`` dump carries ``kind`` +
    (for BI tables) ``columns``/``rows``. We reconstruct a ``ComponentData`` envelope
    only for the artifact peek (matches ``FakeOrchestrator._to_artifact``).
    """
    kind = result.get("kind")
    if kind is None:
        return None
    # Cheap peek without a full ComponentData reconstruction: table-shaped dumps.
    if "columns" in result and "rows" in result:
        return TableArtifact(
            columns=list(result["columns"]),
            rows=[list(r) for r in result["rows"]],
        )
    return None
