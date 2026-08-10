"""Contract-testing DSL for the two narrow waists.

``CopilotResponse`` collects an SSE stream and offers OpenBB-CopilotResponse-style
assertions. M1 ships the DSL + builder helpers; the real StatelessOrchestrator
arrives in M2, but the DSL is self-tested against a fake async-generator orchestrator.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from agentkit_protocol.models import Artifact
from agentkit_protocol.models import BaseSSE
from agentkit_protocol.models import Citation
from agentkit_protocol.models import CopilotCitationCollection
from agentkit_protocol.models import CopilotFunctionCall
from agentkit_protocol.models import CopilotMessageArtifact
from agentkit_protocol.models import CopilotMessageChunk
from agentkit_protocol.models import CopilotPromptSuggestions
from agentkit_protocol.models import Message
from agentkit_protocol.models import QueryRequest
from agentkit_protocol.models import SessionContext


__all__ = ["CopilotResponse", "collect_stream", "human_message", "query"]


class CopilotResponse:
    """Collected SSE stream with OpenBB-style assertion helpers."""

    def __init__(self, events: list[BaseSSE]) -> None:
        """Store the raw event list (copied)."""
        self.events: list[BaseSSE] = list(events)

    @property
    def text(self) -> str:
        """Concatenated text of all copilotMessageChunk events."""
        return "".join(e.text for e in self.events if isinstance(e, CopilotMessageChunk))

    @property
    def artifacts(self) -> list[Artifact]:
        """All artifacts carried by copilotMessageArtifact events."""
        return [e.artifact for e in self.events if isinstance(e, CopilotMessageArtifact)]

    @property
    def function_calls(self) -> list[CopilotFunctionCall]:
        """All copilotFunctionCall events (frontend UI actions requested)."""
        return [e for e in self.events if isinstance(e, CopilotFunctionCall)]

    @property
    def citations(self) -> list[Citation]:
        """All citations across copilotCitationCollection events."""
        out: list[Citation] = []
        for e in self.events:
            if isinstance(e, CopilotCitationCollection):
                out.extend(e.citations)
        return out

    @property
    def suggestions(self) -> list[str]:
        """All follow-up suggestions across copilotPromptSuggestions events."""
        out: list[str] = []
        for e in self.events:
            if isinstance(e, CopilotPromptSuggestions):
                out.extend(e.suggestions)
        return out

    def has_text_containing(self, needle: str) -> bool:
        """True if the concatenated reply text contains ``needle``."""
        return needle in self.text

    def has_artifact(self, kind: str | None = None) -> bool:
        """True if any artifact was emitted; if ``kind`` given, match that kind."""
        if kind is None:
            return len(self.artifacts) > 0
        return any(a.kind == kind for a in self.artifacts)

    def has_function_call(self, name: str | None = None) -> bool:
        """True if any function call was emitted; if ``name`` given, match that verb."""
        if name is None:
            return len(self.function_calls) > 0
        return any(fc.name == name for fc in self.function_calls)

    def __repr__(self) -> str:
        """Concise debug representation."""
        return (
            f"CopilotResponse(events={len(self.events)}, "
            f"text={self.text!r}, artifacts={len(self.artifacts)}, "
            f"function_calls={len(self.function_calls)})"
        )


async def collect_stream(stream: AsyncIterator[BaseSSE]) -> CopilotResponse:
    """Drain an SSE async iterator into a CopilotResponse."""
    events: list[BaseSSE] = []
    async for event in stream:
        events.append(event)
    return CopilotResponse(events)


def human_message(text: str) -> Message:
    """Build a role=human message."""
    return Message(role="human", content=text)


def query(
    text: str,
    *,
    user_identity: str = "tester",
    workspace_id: str = "ws-test",
    trace_id: str = "trace-test",
    user_permissions: list[str] | None = None,
    history: list[Message] | None = None,
    **kwargs: Any,
) -> QueryRequest:
    """Build a minimal QueryRequest for tests.

    Extra keyword args forward to QueryRequest (tools, features, workspace_options, ...).
    """
    messages = list(history or [])
    messages.append(human_message(text))
    return QueryRequest(
        messages=messages,
        session_context=SessionContext(
            user_identity=user_identity,
            user_permissions=user_permissions or [],
            workspace_id=workspace_id,
            trace_id=trace_id,
        ),
        **kwargs,
    )
