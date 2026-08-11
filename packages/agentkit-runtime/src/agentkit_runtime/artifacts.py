"""Build a polymorphic ``Artifact`` from a ``ComponentData`` envelope (example-grade).

Mirrors ``FakeOrchestrator._to_artifact``: peek at the envelope's ``columns``/``rows``
to pick a ``TableArtifact``; otherwise fall back to a ``TextArtifact`` dump. Real
profile-typed artifacts come from profile packages (``agentkit-bi`` chart artifacts,
M3+) — this generic peek is enough for the M2 examples.
"""

from __future__ import annotations

from typing import Any

from agentkit_protocol import Artifact
from agentkit_protocol import ComponentData
from agentkit_protocol import TableArtifact
from agentkit_protocol import TextArtifact


__all__ = ["to_artifact"]


def to_artifact(verb_name: str, data: Any) -> Artifact:
    """Map a ``ComponentData`` envelope onto a renderable ``Artifact``.

    Core never parses ``ComponentData`` content; here we peek at the envelope to pick a
    rendering — BI data carries ``columns``/``rows`` (table); DCC data carries node
    attributes (text dump). The real orchestrator would yield a profile-typed artifact;
    this generic peek is enough for the examples.
    """
    if isinstance(data, ComponentData):
        columns = getattr(data, "columns", None)
        if columns is not None:
            rows = getattr(data, "rows", [])
            return TableArtifact(columns=list(columns), rows=[list(r) for r in rows])
        return TextArtifact(text=data.model_dump_json(indent=2))
    # Non-ComponentData results (e.g. a catalog list) — dump as text.
    return TextArtifact(text=str(data))
