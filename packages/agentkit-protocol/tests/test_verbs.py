"""Contract tests for the standard verb catalogue, VerbSpec -> ToolDef, and verb bindings."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from agentkit_protocol import BACKEND_VERBS
from agentkit_protocol import FRONTEND_VERBS
from agentkit_protocol import STANDARD_VERBS
from agentkit_protocol import ToolDef
from agentkit_protocol import VerbAlias
from agentkit_protocol import VerbBinding
from agentkit_protocol import VerbBindings
from agentkit_protocol import verb_to_tool


async def _handler(ctx, args):
    """Stub handler satisfying the VerbHandler signature."""


def test_standard_verbs_split() -> None:
    """STANDARD_VERBS = 7 backend-sync + 4 frontend-FunctionCall (11 total)."""
    assert len(BACKEND_VERBS) == 7
    assert len(FRONTEND_VERBS) == 4
    assert len(STANDARD_VERBS) == 11
    assert [*BACKEND_VERBS, *FRONTEND_VERBS] == STANDARD_VERBS


def test_verb_to_tool_drops_executes_on() -> None:
    """verb_to_tool builds a ToolDef without executes_on (the LLM must not see the category)."""
    for verb in STANDARD_VERBS:
        tool = verb_to_tool(verb)
        assert isinstance(tool, ToolDef)
        assert tool.name == verb.name
        assert tool.description == verb.description
        assert tool.input_schema == verb.input_schema
        assert not hasattr(tool, "executes_on")


def test_verb_binding_is_frozen() -> None:
    """VerbBinding is an immutable declaration."""
    binding = VerbBinding(name="get_component_data", handler=_handler)
    with pytest.raises(FrozenInstanceError):
        binding.name = "x"


def test_verb_alias_is_frozen() -> None:
    """VerbAlias is an immutable declaration."""
    alias = VerbAlias(name="get_widget_data", target="get_component_data")
    with pytest.raises(FrozenInstanceError):
        alias.target = "x"


def test_verb_bindings_resolve_binding() -> None:
    """Resolve returns the handler for a directly bound verb name."""
    bindings = VerbBindings()
    bindings.bind(VerbBinding(name="get_component_data", handler=_handler))
    assert bindings.resolve("get_component_data") is _handler


def test_verb_bindings_resolve_alias() -> None:
    """Resolve follows an alias to the target verb's handler."""
    bindings = VerbBindings()
    bindings.bind(VerbBinding(name="get_component_data", handler=_handler))
    bindings.alias(VerbAlias(name="get_widget_data", target="get_component_data"))
    assert bindings.resolve("get_widget_data") is _handler


def test_verb_bindings_resolve_unknown_returns_none() -> None:
    """Resolve returns None for an unregistered name."""
    assert VerbBindings().resolve("nope") is None


def test_verb_bindings_names_lists_all() -> None:
    """Names lists both bound verbs and aliases."""
    bindings = VerbBindings()
    bindings.bind(VerbBinding(name="get_component_data", handler=_handler))
    bindings.alias(VerbAlias(name="get_widget_data", target="get_component_data"))
    assert set(bindings.names()) == {"get_component_data", "get_widget_data"}
