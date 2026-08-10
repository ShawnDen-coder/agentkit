"""agentkit-protocol: domain-neutral protocol + framework core (the two narrow waists).

Frozen contracts (M1):
  * Narrow waist ② - SSE protocol: the 6 copilot events + QueryRequest/Message/SessionContext.
  * Narrow waist ① - adapter contract base types: Component / ComponentSchema envelope /
    ComponentAdapter Protocol.

Core is BI-agnostic (agentkit-bi / agentkit-dcc carry domain semantics). See
docs/contracts.md for the frozen surface and versioning policy.

Design note: ``Component.schema_`` is the Python attribute (trailing underscore avoids
shadowing ``BaseModel.schema``); it serializes to the wire key ``schema``.
"""

from __future__ import annotations

from agentkit_protocol.auth import AllowAllAuthorizer
from agentkit_protocol.auth import AuthContext
from agentkit_protocol.auth import AuthenticationError
from agentkit_protocol.auth import Authenticator
from agentkit_protocol.auth import AuthError
from agentkit_protocol.auth import AuthorizationError
from agentkit_protocol.auth import Authorizer
from agentkit_protocol.auth import AuthzAction
from agentkit_protocol.auth import DenyAllAuthorizer
from agentkit_protocol.auth import Principal
from agentkit_protocol.auth import session_from_principal
from agentkit_protocol.helpers import deterministic_uuid
from agentkit_protocol.llm import LlmChunk
from agentkit_protocol.llm import LlmResponse
from agentkit_protocol.llm import LlmToolCall
from agentkit_protocol.llm import ToolDef
from agentkit_protocol.models import PROTOCOL_VERSION
from agentkit_protocol.models import AdapterCapabilities
from agentkit_protocol.models import Artifact
from agentkit_protocol.models import BaseSSE
from agentkit_protocol.models import Citation
from agentkit_protocol.models import Component
from agentkit_protocol.models import ComponentCapabilities
from agentkit_protocol.models import ComponentData
from agentkit_protocol.models import ComponentParam
from agentkit_protocol.models import ComponentSchema
from agentkit_protocol.models import CopilotCitationCollection
from agentkit_protocol.models import CopilotFunctionCall
from agentkit_protocol.models import CopilotMessageArtifact
from agentkit_protocol.models import CopilotMessageChunk
from agentkit_protocol.models import CopilotPromptSuggestions
from agentkit_protocol.models import CopilotStatusUpdate
from agentkit_protocol.models import ErrorArtifact
from agentkit_protocol.models import Field
from agentkit_protocol.models import MarkdownArtifact
from agentkit_protocol.models import Message
from agentkit_protocol.models import MessageRole
from agentkit_protocol.models import QueryRequest
from agentkit_protocol.models import Refinement
from agentkit_protocol.models import SessionContext
from agentkit_protocol.models import TableArtifact
from agentkit_protocol.models import TextArtifact
from agentkit_protocol.protocols import ComponentAdapter
from agentkit_protocol.protocols import LlmClient
from agentkit_protocol.protocols import Orchestrator
from agentkit_protocol.protocols import VerbHandler
from agentkit_protocol.testing import CopilotResponse
from agentkit_protocol.testing import collect_stream
from agentkit_protocol.testing import human_message
from agentkit_protocol.testing import query
from agentkit_protocol.verbs import BACKEND_VERBS
from agentkit_protocol.verbs import FRONTEND_VERBS
from agentkit_protocol.verbs import STANDARD_VERBS
from agentkit_protocol.verbs import VerbAlias
from agentkit_protocol.verbs import VerbBinding
from agentkit_protocol.verbs import VerbBindings
from agentkit_protocol.verbs import VerbCategory
from agentkit_protocol.verbs import VerbSpec
from agentkit_protocol.verbs import verb_to_tool


__all__ = [
    "BACKEND_VERBS",
    "FRONTEND_VERBS",
    "PROTOCOL_VERSION",
    "STANDARD_VERBS",
    "AdapterCapabilities",
    "AllowAllAuthorizer",
    "Artifact",
    "AuthContext",
    "AuthError",
    "AuthenticationError",
    "Authenticator",
    "AuthorizationError",
    "Authorizer",
    "AuthzAction",
    "BaseSSE",
    "Citation",
    "Component",
    "ComponentAdapter",
    "ComponentCapabilities",
    "ComponentData",
    "ComponentParam",
    "ComponentSchema",
    "CopilotCitationCollection",
    "CopilotFunctionCall",
    "CopilotMessageArtifact",
    "CopilotMessageChunk",
    "CopilotPromptSuggestions",
    "CopilotResponse",
    "CopilotStatusUpdate",
    "DenyAllAuthorizer",
    "ErrorArtifact",
    "Field",
    "LlmChunk",
    "LlmClient",
    "LlmResponse",
    "LlmToolCall",
    "MarkdownArtifact",
    "Message",
    "MessageRole",
    "Orchestrator",
    "Principal",
    "QueryRequest",
    "Refinement",
    "SessionContext",
    "TableArtifact",
    "TextArtifact",
    "ToolDef",
    "VerbAlias",
    "VerbBinding",
    "VerbBindings",
    "VerbCategory",
    "VerbHandler",
    "VerbSpec",
    "collect_stream",
    "deterministic_uuid",
    "human_message",
    "query",
    "session_from_principal",
    "verb_to_tool",
]
