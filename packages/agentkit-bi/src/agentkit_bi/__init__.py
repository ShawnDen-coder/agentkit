"""agentkit-bi: BI domain profile for agentkit.

Carries BI semantics that the domain-neutral agentkit-core omits:
BiSemanticModel, Widget, WidgetData, BiRefinement, BI capabilities, ChartArtifact,
BiAdapter base, BI verb aliases, and the BI system-prompt builder.
"""

from __future__ import annotations

from agentkit_bi.adapter import BiAdapter
from agentkit_bi.artifacts import ChartArtifact
from agentkit_bi.models import BiAdapterCapabilities
from agentkit_bi.models import BiRefinement
from agentkit_bi.models import BiSemanticModel
from agentkit_bi.models import CalculatedField
from agentkit_bi.models import DrillPath
from agentkit_bi.models import FilterSpec
from agentkit_bi.models import Widget
from agentkit_bi.models import WidgetCapabilities
from agentkit_bi.models import WidgetData
from agentkit_bi.models import WidgetParam
from agentkit_bi.prompt import build_bi_system_prompt
from agentkit_bi.verbs import BI_EXTRA_VERBS
from agentkit_bi.verbs import BI_VERB_ALIASES


__all__ = [
    "BI_EXTRA_VERBS",
    "BI_VERB_ALIASES",
    "BiAdapter",
    "BiAdapterCapabilities",
    "BiRefinement",
    "BiSemanticModel",
    "CalculatedField",
    "ChartArtifact",
    "DrillPath",
    "FilterSpec",
    "Widget",
    "WidgetCapabilities",
    "WidgetData",
    "WidgetParam",
    "build_bi_system_prompt",
]
