"""LLM result + tool-definition types (provider-neutral).

These let the orchestrator route LLM tool calls (backend sync vs frontend FunctionCall)
without depending on any LLM provider SDK. The ``LlmClient`` impl
(agentkit-llm-langchain) converts between these and langchain's own types.

Added in 0.2.0 (PROTOCOL_VERSION minor bump): ``LlmClient`` is tightened to return
these instead of ``Any``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field as PydanticField


__all__ = ["LlmChunk", "LlmResponse", "LlmToolCall", "ToolDef"]


class ToolDef(BaseModel):
    """A provider-neutral tool definition exposed to the LLM.

    Built from a ``VerbSpec`` (name/description/input_schema). The ``executes_on``
    category is deliberately NOT included - the LLM must not see it; the orchestrator
    routes by it after the LLM emits a tool call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    input_schema: dict[str, Any] = PydanticField(default_factory=dict)


class LlmToolCall(BaseModel):
    """A tool call requested by the LLM (provider-neutral)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any] = PydanticField(default_factory=dict)


class LlmChunk(BaseModel):
    """A streamed chunk from the LLM (text delta)."""

    model_config = ConfigDict(extra="forbid")

    text: str


class LlmResponse(BaseModel):
    """A full (non-streaming) LLM response: text content and/or tool calls.

    Phase 1 of the Option B loop calls ``LlmClient.call`` with tools to obtain this.
    If ``tool_calls`` is non-empty the orchestrator routes them (backend sync, or
    frontend FunctionCall); otherwise ``content`` is the answer (yielded as chunks).
    """

    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[LlmToolCall] = PydanticField(default_factory=list)
