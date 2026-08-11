"""Scripted ``Orchestrator`` for the examples (no LLM, no agentkit-runtime yet).

Implements the ``Orchestrator`` Protocol with canned behavior that exercises the
Option B state machine and 5 of the 6 SSE events, using the REAL adapter for the
backend-sync path (so narrow waist ① is genuine, not faked). When
``agentkit-runtime`` (M2, langchain/langgraph first-class) lands, swap this for
``LanggraphOrchestrator`` - the adapter, auth, frontend, and SSE wiring in the
examples are unchanged. That swap is the teaching point: the wire contract
(``agentkit_protocol``) is the stable seam; the orchestrator is the swappable
implementation.

State machine demonstrated:
  * role=human  -> backend sync (real adapter calls) + yield a frontend
                   ``CopilotFunctionCall`` (round-trip begins, stream ends).
  * role=tool   -> resume: yield the final answer + suggestions (round-trip ends).

This mirrors the wire-level Option B contract (§6.3) regardless of whether the
real impl is stateless (state in ``request.messages``) or uses a langgraph
checkpoint. The FakeOrchestrator is stateless for simplicity.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentkit_protocol import BaseSSE
from agentkit_protocol import ComponentAdapter
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import QueryRequest
from agentkit_protocol import TableArtifact
from agentkit_protocol import TextArtifact
from agentkit_protocol.protocols import Orchestrator


class FakeOrchestrator(Orchestrator):
    """Scripted orchestrator: real adapter calls, no LLM, deterministic."""

    def __init__(self, adapter: ComponentAdapter) -> None:
        """Hold the adapter; backend-sync verbs call it directly (no VerbBindings yet)."""
        self._adapter = adapter

    async def run(self, request: QueryRequest) -> AsyncIterator[BaseSSE]:
        """Yield the SSE stream for a query (async generator, not a coroutine)."""
        last = request.messages[-1]
        if last.role == "tool":
            # Resume from a frontend FunctionCall round-trip (Option B).
            yield CopilotMessageChunk(text="已完成 - 组件已添加到仪表盘。")
            yield CopilotPromptSuggestions(
                suggestions=[
                    "再看一个组件",
                    "按地区筛选",
                    "解释一下这些数字",
                ]
            )
            return

        # role=human: backend sync (real adapter calls; the real orchestrator would
        # route these as langchain tool-calls via VerbBindings - same adapter calls).
        ctx = request.session_context
        yield CopilotStatusUpdate(status="thinking", label="正在获取目录")
        catalog = await self._adapter.list_components(ctx)
        if not catalog:
            yield CopilotMessageChunk(text="没有可用组件。")
            return

        yield CopilotStatusUpdate(status="running", label="正在获取数据")
        data = await self._adapter.get_component_data(ctx, catalog[0], {})
        yield CopilotMessageArtifact(artifact=self._to_artifact(catalog[0].name, data))

        # Simulate "the LLM decided to add this widget to the dashboard" -> the
        # frontend must execute this UI action (Option B frontend FunctionCall).
        yield CopilotFunctionCall(
            name="add_component_to_dashboard",
            arguments={"component_id": catalog[0].component_id},
        )
        # Stream ends here; the frontend re-POSTs role=tool to resume.

    @staticmethod
    def _to_artifact(name: str, data: Any) -> TableArtifact | TextArtifact:
        """Build an artifact from the polymorphic ComponentData envelope.

        Core never parses ``ComponentData`` content; here we peek at the envelope
        to pick a rendering. BI data carries ``columns``/``rows`` (table); DCC data
        carries node attributes (text dump). The real orchestrator would yield a
        profile-typed artifact; this generic peek is enough for the examples.
        """
        columns = getattr(data, "columns", None)
        if columns is not None:
            rows = getattr(data, "rows", [])
            return TableArtifact(columns=list(columns), rows=[list(r) for r in rows])
        return TextArtifact(text=f"{name}\n\n{data.model_dump_json(indent=2)}")
