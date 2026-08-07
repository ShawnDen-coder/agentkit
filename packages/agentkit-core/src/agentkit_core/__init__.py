"""agentkit-core: domain-neutral protocol + framework core (the two narrow waists).

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

from agentkit_core.helpers import deterministic_uuid
from agentkit_core.models import PROTOCOL_VERSION
from agentkit_core.models import AdapterCapabilities
from agentkit_core.models import Artifact
from agentkit_core.models import BaseSSE
from agentkit_core.models import Citation
from agentkit_core.models import Component
from agentkit_core.models import ComponentCapabilities
from agentkit_core.models import ComponentData
from agentkit_core.models import ComponentParam
from agentkit_core.models import ComponentSchema
from agentkit_core.models import CopilotCitationCollection
from agentkit_core.models import CopilotFunctionCall
from agentkit_core.models import CopilotMessageArtifact
from agentkit_core.models import CopilotMessageChunk
from agentkit_core.models import CopilotPromptSuggestions
from agentkit_core.models import CopilotStatusUpdate
from agentkit_core.models import ErrorArtifact
from agentkit_core.models import Field
from agentkit_core.models import MarkdownArtifact
from agentkit_core.models import Message
from agentkit_core.models import MessageRole
from agentkit_core.models import QueryRequest
from agentkit_core.models import Refinement
from agentkit_core.models import SessionContext
from agentkit_core.models import TableArtifact
from agentkit_core.models import TextArtifact
from agentkit_core.protocols import ComponentAdapter
from agentkit_core.protocols import LlmClient
from agentkit_core.protocols import Orchestrator
from agentkit_core.protocols import VerbHandler
from agentkit_core.testing import CopilotResponse
from agentkit_core.testing import collect_stream
from agentkit_core.testing import human_message
from agentkit_core.testing import query
from agentkit_core.verbs import BACKEND_VERBS
from agentkit_core.verbs import FRONTEND_VERBS
from agentkit_core.verbs import STANDARD_VERBS
from agentkit_core.verbs import VerbCategory
from agentkit_core.verbs import VerbSpec


__all__ = [
    "BACKEND_VERBS",
    "FRONTEND_VERBS",
    "PROTOCOL_VERSION",
    "STANDARD_VERBS",
    "AdapterCapabilities",
    "Artifact",
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
    "ErrorArtifact",
    "Field",
    "LlmClient",
    "MarkdownArtifact",
    "Message",
    "MessageRole",
    "Orchestrator",
    "QueryRequest",
    "Refinement",
    "SessionContext",
    "TableArtifact",
    "TextArtifact",
    "VerbCategory",
    "VerbHandler",
    "VerbSpec",
    "collect_stream",
    "deterministic_uuid",
    "human_message",
    "query",
]
