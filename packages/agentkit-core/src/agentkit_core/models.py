"""agentkit-core protocol models: the two narrow waists, frozen.

Freezes:
  * Narrow waist ② (SSE protocol) - the 6 copilot events + QueryRequest/Message/SessionContext.
  * Narrow waist ① (adapter contract) base types - Component / ComponentSchema envelope /
    ComponentCapabilities / AdapterCapabilities. The ComponentAdapter Protocol itself
    lives in :mod:`agentkit_core.protocols`.

Core is domain-neutral. Domain schemas (BiSemanticModel, DccSchema) and artifacts
(chart) live in profile packages (agentkit-bi, agentkit-dcc). Core NEVER parses the
content of a ComponentSchema or Artifact: they are polymorphic envelopes
(``kind`` discriminator + ``extra="allow"``), and subclass-typed fields use
``SerializeAsAny`` so profile payloads survive JSON round-trip through core unchanged.
"""

from __future__ import annotations

from typing import Any
from typing import ClassVar
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field as PydanticField
from pydantic import SecretStr
from pydantic import SerializeAsAny


__all__ = [
    "PROTOCOL_VERSION",
    "AdapterCapabilities",
    "Artifact",
    "BaseSSE",
    "Citation",
    "Component",
    "ComponentCapabilities",
    "ComponentData",
    "ComponentParam",
    "ComponentSchema",
    "CopilotCitationCollection",
    "CopilotFunctionCall",
    "CopilotMessageArtifact",
    "CopilotMessageChunk",
    "CopilotPromptSuggestions",
    "CopilotStatusUpdate",
    "ErrorArtifact",
    "Field",
    "MarkdownArtifact",
    "Message",
    "MessageRole",
    "QueryRequest",
    "Refinement",
    "SessionContext",
    "TableArtifact",
    "TextArtifact",
]

PROTOCOL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Generic field + envelope primitives (shared across profiles)
# ---------------------------------------------------------------------------


class Field(BaseModel):
    """A generic named field. Shared by BI (dimensions/measures) and DCC (attributes)."""

    model_config = ConfigDict(extra="allow")

    name: str
    dtype: str | None = None  # "string" | "number" | "date" | ...
    label: str | None = None
    description: str | None = None


class ComponentParam(BaseModel):
    """A parameter a component accepts (filter value, time range, ...)."""

    model_config = ConfigDict(extra="allow")

    name: str
    type: str
    value: Any | None = None
    default: Any | None = None
    required: bool = False
    label: str | None = None


class ComponentCapabilities(BaseModel):
    """Per-component capability flags. Domain-neutral base; profiles extend.

    agentkit-bi defines ``WidgetCapabilities`` adding can_filter/can_drill/can_export.
    Core does not read profile-specific flags.
    """

    model_config = ConfigDict(extra="allow")


class ComponentSchema(BaseModel):
    """Polymorphic schema envelope. Core does NOT parse content.

    Profiles subclass with a ``kind`` Literal + typed fields, e.g. agentkit-bi's
    ``BiSemanticModel`` (kind="bi.semantic"). Adapters return profile-typed instances;
    core serializes them transparently (subclass fields preserved via SerializeAsAny)
    and deserializes them back as this opaque base (profile fields kept via
    ``extra="allow"``).
    """

    model_config = ConfigDict(extra="allow")

    kind: str


class ComponentData(BaseModel):
    """Polymorphic data envelope returned by ``get_component_data``.

    Profiles subclass with typed payloads (BI: columns/rows; DCC: scene graph).
    """

    model_config = ConfigDict(extra="allow")

    kind: str


class Refinement(BaseModel):
    """Polymorphic refinement envelope for ``refine_component``.

    Profiles subclass (BI: filters/drill/measure swap). Core treats as opaque.
    """

    model_config = ConfigDict(extra="allow")

    kind: str


class AdapterCapabilities(BaseModel):
    """Per-adapter capability flags. Domain-neutral base; profiles extend.

    Core holds genuinely cross-domain flags; profiles add domain flags (BI:
    can_filter/can_drill/can_add_widget/supports_semantic_model). Capability
    negotiation (§5.2) reads core flags in core; profile flags in the profile.
    """

    model_config = ConfigDict(extra="allow")

    supports_catalog: bool = False
    supports_selection: bool = False
    max_concurrent_fetch: int = 1


class Component(BaseModel):
    """A domain-neutral component (a BI widget, a DCC scene node, ...).

    ``schema_`` carries the profile-typed semantic description; core treats it as an
    opaque envelope. The Python attribute is ``schema_`` (trailing underscore avoids
    shadowing ``BaseModel.schema``); it serializes to the wire key ``schema``.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    component_id: str
    origin: str  # "superset" | "metabase" | "maya" | ...
    name: str
    params: list[ComponentParam] = PydanticField(default_factory=list)
    capabilities: ComponentCapabilities = PydanticField(default_factory=ComponentCapabilities)
    schema_: SerializeAsAny[ComponentSchema] | None = PydanticField(default=None, alias="schema")


# ---------------------------------------------------------------------------
# Artifacts (carried by CopilotMessageArtifact)
# ---------------------------------------------------------------------------


class Artifact(BaseModel):
    """Polymorphic artifact envelope. Core defines generic kinds; profiles extend."""

    model_config = ConfigDict(extra="allow")

    kind: str


class TextArtifact(Artifact):
    """A plain-text artifact."""

    kind: Literal["text"] = "text"
    text: str


class MarkdownArtifact(Artifact):
    """A Markdown-formatted artifact."""

    kind: Literal["markdown"] = "markdown"
    markdown: str


class TableArtifact(Artifact):
    """A tabular artifact (columns + rows)."""

    kind: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]] = PydanticField(default_factory=list)


class ErrorArtifact(Artifact):
    """An error artifact (e.g. a failed tool result)."""

    kind: Literal["error"] = "error"
    message: str


class Citation(BaseModel):
    """A citation backing part of the answer."""

    model_config = ConfigDict(extra="allow")

    title: str
    url: str | None = None
    snippet: str | None = None


# ---------------------------------------------------------------------------
# SSE wire envelope + 6 events (narrow waist ②)
# ---------------------------------------------------------------------------


class BaseSSE(BaseModel):
    """Base for the 6 copilot SSE events.

    Wire contract (consumed by FastAPI ``EventSourceResponse``)::

        {"event": <event name>, "data": <json string of payload>}

    ``event`` is a class-level discriminator, not a model field, so it is not
    duplicated inside ``data``.
    """

    model_config = ConfigDict(extra="forbid")

    event: ClassVar[str]

    def to_sse(self) -> dict[str, str]:
        """Return the ``{"event", "data"}`` dict for SSE transport."""
        return {
            "event": self.event,
            "data": self.model_dump_json(by_alias=True, exclude_none=True),
        }


class CopilotMessageChunk(BaseSSE):
    """A streamed text delta of the assistant's reply."""

    event: ClassVar[str] = "copilotMessageChunk"
    text: str
    message_id: str | None = None


class CopilotStatusUpdate(BaseSSE):
    """Lifecycle/status signal (thinking, fetching data, idle ...)."""

    event: ClassVar[str] = "copilotStatusUpdate"
    status: str
    label: str | None = None


class CopilotMessageArtifact(BaseSSE):
    """A structured artifact (chart/table/text/...) to render in the UI."""

    event: ClassVar[str] = "copilotMessageArtifact"
    artifact: SerializeAsAny[Artifact]
    message_id: str | None = None


class CopilotFunctionCall(BaseSSE):
    """Ask the frontend to execute a UI verb (Option B: frontend FunctionCall only).

    Carries the verb name + arguments; the frontend executes, then re-POSTs with a
    ``role=tool`` message containing the result. Reserved for UI actions only
    (add/update/manage_nav/assign_tasks); data/skill/MCP go via backend sync calls.
    """

    event: ClassVar[str] = "copilotFunctionCall"
    name: str
    arguments: dict[str, Any] = PydanticField(default_factory=dict)


class CopilotCitationCollection(BaseSSE):
    """Citations backing the answer."""

    event: ClassVar[str] = "copilotCitationCollection"
    citations: list[Citation]


class CopilotPromptSuggestions(BaseSSE):
    """Follow-up prompt suggestions."""

    event: ClassVar[str] = "copilotPromptSuggestions"
    suggestions: list[str]


# ---------------------------------------------------------------------------
# Request / session
# ---------------------------------------------------------------------------

MessageRole = Literal["human", "tool", "assistant", "system"]


class SessionContext(BaseModel):
    """Carries user identity + permissions + BI auth token; the RLS passthrough vehicle.

    ``auth_token`` is the user's BI token for Option B backend-fetch (the orchestrator
    calls the adapter on the user's behalf). Transported via HTTP ``Authorization``
    header (extracted by the FastAPI layer), NOT the request body. It is ``SecretStr``
    with ``exclude=True`` so it is never serialized into ``model_dump()`` / JSON / logs
    (§10: short-lived, not logged/cached, transport-encrypted, scoped to the workspace).
    Adapters read it via ``ctx.auth_token.get_secret_value()``.
    """

    model_config = ConfigDict(extra="forbid")

    user_identity: str
    user_permissions: list[str] = PydanticField(default_factory=list)
    workspace_id: str
    trace_id: str
    auth_token: SecretStr | None = PydanticField(default=None, exclude=True)


class Message(BaseModel):
    """A single conversation message. ``role`` drives the state machine (§6.3).

    - role=human: run the agent (sync multi-hop fetch + stream).
    - role=tool: a frontend UI action result returned via the FunctionCall loop.
    - role=assistant/system: history context.
    """

    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str | None = None
    name: str | None = None  # role=tool: the verb name whose result this carries
    data: dict[str, Any] | None = None  # role=tool: structured result payload


class QueryRequest(BaseModel):
    """Inbound request. Stateless: all state lives in ``messages``."""

    model_config = ConfigDict(extra="forbid")

    messages: list[Message]
    session_context: SessionContext
    protocol_version: str = PROTOCOL_VERSION
    tools: list[dict[str, Any]] | None = None  # per-agent MCP function defs (§8.2 mode A)
    features: dict[str, bool] | None = None  # boolean feature gates (frontend injection)
    workspace_options: dict[str, Any] | None = None  # object-form user toggles (§4.1)
