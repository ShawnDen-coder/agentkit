"""BI verb aliases + extra BI verbs.

Per §D.4, the profile may register domain aliases mapping BI-flavored verb names to
the canonical core verbs, plus BI-specific extras (e.g. export_artifact). The live
alias resolution is wired in M2 (agentkit-runtime VerbRegistry); M1 freezes the
mapping.
"""

from __future__ import annotations

from agentkit_core import VerbSpec


__all__ = ["BI_EXTRA_VERBS", "BI_VERB_ALIASES"]

# BI-flavored alias -> canonical core verb name.
BI_VERB_ALIASES: dict[str, str] = {
    "get_widget_data": "get_component_data",
    "refine_widget": "refine_component",
    "get_widget_catalog": "get_catalog",
}

# BI-specific verbs not in the core catalogue.
BI_EXTRA_VERBS: list[VerbSpec] = [
    VerbSpec(
        name="export_artifact",
        description="Export the current insight as CSV / PDF / subscription (frontend UI action).",
        executes_on="frontend",
        input_schema={
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["csv", "pdf", "subscription"]},
                "component_id": {"type": "string"},
            },
            "required": ["format"],
        },
    ),
]
