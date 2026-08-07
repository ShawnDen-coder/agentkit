"""BI system prompt builder (§6.5).

Assembles the dynamic system prompt from four dimensions: adapter capabilities,
available components (catalog), loaded skills, and user toggles. M1 ships a skeleton;
the orchestrator wires the full 4-dimensional assembly in M2.
"""

from __future__ import annotations

from typing import Any

from agentkit_core import Component

from agentkit_bi.models import BiAdapterCapabilities


__all__ = ["build_bi_system_prompt"]


def build_bi_system_prompt(
    *,
    capabilities: BiAdapterCapabilities,
    components: list[Component] | None = None,
    active_skills: list[str] | None = None,
    toggles: dict[str, Any] | None = None,
) -> str:
    """Build the BI system prompt (§6.5). M1 skeleton; full integration in M2.

    When no components are available, the prompt guides the user to add a widget
    rather than letting the LLM fabricate data (inherited from OpenBB example 99).
    """
    lines: list[str] = [
        "You are a BI data assistant embedded in the user's BI tool.",
        "Understand widgets via their semantic model (dimensions/measures/drill paths),",
        "and refine them (filter / drill / swap measure) through the provided tools.",
        "",
        "## Capabilities",
        f"- list widgets: {capabilities.supports_catalog}",
        f"- filter: {capabilities.can_filter}",
        f"- drill: {capabilities.can_drill}",
        f"- add widget to dashboard: {capabilities.can_add_widget}",
        f"- semantic model: {capabilities.supports_semantic_model}",
    ]

    if components:
        lines.append("")
        lines.append("## Available widgets")
        for c in components:
            lines.append(f"- {c.name} (id={c.component_id}, origin={c.origin})")
    else:
        lines.append("")
        lines.append(
            "## Available widgets\nNone yet. Ask the user to select or add a widget "
            "before answering data questions; do not fabricate data."
        )

    if active_skills:
        lines.append("")
        lines.append("## Active skills")
        lines.extend(f"- {s}" for s in active_skills)

    if toggles:
        lines.append("")
        lines.append("## User toggles")
        for k, v in toggles.items():
            lines.append(f"- {k}: {v}")

    # TODO(M2): orchestrator injects the live tool list + skill prompt fragments.
    return "\n".join(lines)
