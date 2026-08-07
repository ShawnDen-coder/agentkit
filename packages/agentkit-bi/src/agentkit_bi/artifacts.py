"""BI artifacts: the chart artifact (kind="chart"), extending core's Artifact envelope."""

from __future__ import annotations

from typing import Literal

from agentkit_core import Artifact
from pydantic import Field as PydanticField


__all__ = ["ChartArtifact"]


class ChartArtifact(Artifact):
    """A BI chart to render. Carries chart type + axis mappings (§D.2).

    Flows through CopilotMessageArtifact.artifact as an opaque envelope; the BI
    frontend renders it. Cross-BI chart-type coverage is an open consistency question
    (not yet a frozen contract) - see docs/contracts.md.
    """

    kind: Literal["chart"] = "chart"
    chart_type: str  # "bar" | "line" | "pie" | "scatter" | "table" | ...
    x_key: str | None = None
    y_keys: list[str] = PydanticField(default_factory=list)
    title: str | None = None
