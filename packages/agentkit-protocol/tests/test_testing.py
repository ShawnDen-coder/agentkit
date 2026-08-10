"""Tests for the CopilotResponse contract-testing DSL."""

from __future__ import annotations

from collections.abc import AsyncIterator

from agentkit_protocol import BaseSSE
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import TableArtifact
from agentkit_protocol import collect_stream
from agentkit_protocol import human_message
from agentkit_protocol import query


async def _fake_stream() -> AsyncIterator[BaseSSE]:
    """A representative SSE stream: chunks, artifact, function call, suggestions."""
    yield CopilotMessageChunk(text="Hello ")
    yield CopilotMessageChunk(text="world")
    yield CopilotMessageArtifact(artifact=TableArtifact(columns=["a"], rows=[[1]]))
    yield CopilotFunctionCall(name="add_component_to_dashboard", arguments={"component_id": "w1"})
    yield CopilotPromptSuggestions(suggestions=["next?"])


async def _empty_stream() -> AsyncIterator[BaseSSE]:
    """Yield nothing (empty async generator)."""
    return
    yield  # makes this function an async generator


async def test_collect_stream_and_assertions() -> None:
    """collect_stream drains an SSE iterator and assertions read back correctly."""
    resp = await collect_stream(_fake_stream())
    assert resp.has_text_containing("Hello world")
    assert resp.text == "Hello world"
    assert resp.has_artifact("table")
    assert not resp.has_artifact("chart")
    assert resp.has_function_call("add_component_to_dashboard")
    assert not resp.has_function_call("get_catalog")
    assert resp.suggestions == ["next?"]
    assert len(resp.events) == 5


async def test_empty_stream() -> None:
    """An empty stream yields an empty CopilotResponse with falsy assertions."""
    resp = await collect_stream(_empty_stream())
    assert resp.text == ""
    assert not resp.has_artifact()
    assert not resp.has_function_call()
    assert resp.artifacts == []


def test_query_builder() -> None:
    """query() builds a QueryRequest with a human message + session context."""
    req = query("drill by region", user_identity="alice")
    assert req.messages[-1].role == "human"
    assert req.messages[-1].content == "drill by region"
    assert req.session_context.user_identity == "alice"
    assert req.protocol_version


def test_query_builder_with_history() -> None:
    """query() prepends history before the new human message."""
    req = query("next?", history=[human_message("first")])
    assert len(req.messages) == 2
    assert req.messages[0].content == "first"
    assert req.messages[1].content == "next?"


def test_human_message() -> None:
    """human_message builds a role=human message."""
    m = human_message("hi")
    assert m.role == "human"
    assert m.content == "hi"
