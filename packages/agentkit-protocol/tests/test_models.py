"""Contract tests for agentkit-protocol models (the two narrow waists)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agentkit_protocol import PROTOCOL_VERSION
from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import BaseSSE
from agentkit_protocol import Component
from agentkit_protocol import ComponentCapabilities
from agentkit_protocol import ComponentSchema
from agentkit_protocol import CopilotCitationCollection
from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import ErrorArtifact
from agentkit_protocol import Field
from agentkit_protocol import MarkdownArtifact
from agentkit_protocol import Message
from agentkit_protocol import QueryRequest
from agentkit_protocol import SessionContext
from agentkit_protocol import TableArtifact
from agentkit_protocol import TextArtifact
from agentkit_protocol import deterministic_uuid


# -- Narrow waist ②: SSE 6 events -----------------------------------------


@pytest.mark.parametrize(
    "event,expected_name",
    [
        (CopilotMessageChunk(text="hi"), "copilotMessageChunk"),
        (CopilotStatusUpdate(status="thinking"), "copilotStatusUpdate"),
        (CopilotMessageArtifact(artifact=TextArtifact(text="x")), "copilotMessageArtifact"),
        (CopilotFunctionCall(name="get_catalog"), "copilotFunctionCall"),
        (CopilotCitationCollection(citations=[]), "copilotCitationCollection"),
        (CopilotPromptSuggestions(suggestions=["a"]), "copilotPromptSuggestions"),
    ],
)
def test_sse_event_name(event: BaseSSE, expected_name: str) -> None:
    """Each of the 6 SSE events reports its wire event name."""
    assert event.event == expected_name


def test_sse_to_sse_contract() -> None:
    """to_sse returns {"event": str, "data": json-string} per §4.1."""
    ev = CopilotMessageChunk(text="hello", message_id="m1")
    wire = ev.to_sse()
    assert set(wire.keys()) == {"event", "data"}
    assert wire["event"] == "copilotMessageChunk"
    payload = json.loads(wire["data"])
    assert payload["text"] == "hello"
    assert payload["message_id"] == "m1"


def test_sse_exclude_none() -> None:
    """None fields are dropped from the wire data."""
    ev = CopilotMessageChunk(text="hi")  # message_id=None
    payload = json.loads(ev.to_sse()["data"])
    assert "message_id" not in payload


def test_sse_extra_forbidden() -> None:
    """SSE events forbid unknown fields (strict contract)."""
    with pytest.raises(ValidationError):
        CopilotMessageChunk(text="hi", bogus=1)  # type: ignore[call-arg]


def test_artifact_serialize_as_any() -> None:
    """A profile artifact (TableArtifact) survives serialization through the Artifact base."""
    ev = CopilotMessageArtifact(artifact=TableArtifact(columns=["a", "b"], rows=[[1, 2]]))
    payload = json.loads(ev.to_sse()["data"])
    assert payload["artifact"]["kind"] == "table"
    assert payload["artifact"]["columns"] == ["a", "b"]
    assert payload["artifact"]["rows"] == [[1, 2]]


def test_generic_artifacts() -> None:
    """The 4 core artifact kinds construct and serialize."""
    assert TextArtifact(text="t").kind == "text"
    assert MarkdownArtifact(markdown="# h").kind == "markdown"
    assert ErrorArtifact(message="boom").kind == "error"
    t = TableArtifact(columns=["c"])
    assert t.rows == []


# -- Narrow waist ①: Component / ComponentSchema envelope ------------------


def test_component_schema_envelope_roundtrip() -> None:
    """A profile-typed schema survives JSON round-trip through core's opaque envelope."""
    schema = ComponentSchema(kind="bi.semantic", dimensions=[{"name": "region"}])
    comp = Component(component_id="w1", origin="superset", name="Sales", schema=schema)
    j = comp.model_dump_json(by_alias=True)
    # wire key is "schema" (alias), not "schema_"
    assert '"schema":{"kind":"bi.semantic"' in j
    reparsed = Component.model_validate_json(j)
    assert reparsed.schema_ is not None
    assert reparsed.schema_.kind == "bi.semantic"
    # profile fields preserved as extras
    assert "dimensions" in reparsed.schema_.model_dump()


def test_component_schema_none_default() -> None:
    """Component defaults: schema_ None, params [], capabilities empty."""
    comp = Component(component_id="w1", origin="superset", name="Sales")
    assert comp.schema_ is None
    assert comp.params == []
    assert isinstance(comp.capabilities, ComponentCapabilities)


def test_component_extra_allowed() -> None:
    """Component allows profile-specific extra fields (forward-compat)."""
    comp = Component.model_validate(
        {
            "component_id": "w1",
            "origin": "superset",
            "name": "Sales",
            "custom_field": 42,
        }
    )
    assert comp.model_dump()["custom_field"] == 42


def test_field_extra_allowed() -> None:
    """Field is a shared envelope (BI + DCC) and allows extra metadata."""
    f = Field(name="region", dtype="string", display_order=1)
    assert f.model_dump()["display_order"] == 1


def test_adapter_capabilities_core_flags() -> None:
    """AdapterCapabilities holds cross-domain flags; profiles extend via extras."""
    cap = AdapterCapabilities()
    assert cap.supports_catalog is False
    assert cap.max_concurrent_fetch == 1
    cap2 = AdapterCapabilities.model_validate({"supports_catalog": True, "can_filter": True})
    assert cap2.supports_catalog is True
    assert cap2.model_dump()["can_filter"] is True


# -- deterministic_uuid ----------------------------------------------------


def test_deterministic_uuid_stable() -> None:
    """Same inputs -> same UUID, forever; different inputs -> different UUID."""
    a = deterministic_uuid("superset", "w1")
    b = deterministic_uuid("superset", "w1")
    assert a == b
    assert deterministic_uuid("superset", "w2") != a
    assert deterministic_uuid("metabase", "w1") != a


def test_deterministic_uuid_format() -> None:
    """UUID is a 16-char xxh64 hex digest."""
    uid = deterministic_uuid("superset", "w1")
    assert isinstance(uid, str)
    assert len(uid) == 16


# -- Request / session / role state machine --------------------------------


def test_query_request_defaults() -> None:
    """QueryRequest defaults protocol_version and optional fields."""
    req = QueryRequest(
        messages=[Message(role="human", content="hi")],
        session_context=SessionContext(user_identity="u1", workspace_id="ws1", trace_id="t1"),
    )
    assert req.protocol_version == PROTOCOL_VERSION
    assert req.tools is None
    assert req.features is None


def test_message_roles() -> None:
    """Role drives the state machine (§6.3); all four roles construct."""
    for role in ("human", "tool", "assistant", "system"):
        m = Message(role=role)
        assert m.role == role


def test_query_request_roundtrip() -> None:
    """QueryRequest serializes and reparses with role=tool UI-action results intact."""
    req = QueryRequest(
        messages=[
            Message(role="human", content="drill by region"),
            Message(role="tool", name="add_component_to_dashboard", data={"ok": True}),
        ],
        session_context=SessionContext(
            user_identity="u1",
            user_permissions=["read:sales"],
            workspace_id="ws1",
            trace_id="t1",
        ),
    )
    j = req.model_dump_json()
    reparsed = QueryRequest.model_validate_json(j)
    assert reparsed.messages[1].role == "tool"
    assert reparsed.messages[1].name == "add_component_to_dashboard"
    assert reparsed.session_context.user_permissions == ["read:sales"]
