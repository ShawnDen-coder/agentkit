"""ComponentAdapter for NodeGraphQt: the narrow-waist ① impl.

``NodeGraphQtAdapter`` wraps a ``NodeGraph`` and exposes its nodes as agentkit
``Component`` objects. This is the only contract a host-tool adapter implements
(§C.1); the orchestrator calls these methods via ``build_adapter_tools``.

Node identification: each node is identified by its display ``name()`` (unique
within the graph). The ``component_id`` on the wire is the node name.
"""

from __future__ import annotations

from typing import Any

from NodeGraphQt import BaseNode
from NodeGraphQt import NodeGraph

from agentkit_protocol import AdapterCapabilities
from agentkit_protocol import Component
from agentkit_protocol import ComponentData
from agentkit_protocol import ComponentSchema
from agentkit_protocol import Refinement
from agentkit_protocol import SessionContext


__all__ = ["NodeGraphQtAdapter"]


# ---------------------------------------------------------------------------
# Node type metadata (for semantic model)
# ---------------------------------------------------------------------------


# Maps node class name → (input ports, output ports, widget fields).
# Used by get_semantic_model to describe a node's port schema.
_NODE_PORT_SCHEMA: dict[str, dict[str, Any]] = {
    "NumberNode": {"inputs": [], "outputs": ["value"], "widget": "spinbox"},
    "StringNode": {"inputs": [], "outputs": ["value"], "widget": "text"},
    "AddNode": {"inputs": ["a", "b"], "outputs": ["result"], "widget": None},
    "SubtractNode": {"inputs": ["a", "b"], "outputs": ["result"], "widget": None},
    "MultiplyNode": {"inputs": ["a", "b"], "outputs": ["result"], "widget": None},
    "OutputNode": {"inputs": ["value"], "outputs": [], "widget": None},
}


class NodeGraphQtAdapter:
    """ComponentAdapter impl backed by a NodeGraphQt ``NodeGraph``.

    The adapter is domain-neutral (returns ``Component``/``ComponentData``/
    ``ComponentSchema`` envelopes). Domain-specific node semantics live in the
    node classes themselves; the adapter just reads/writes their properties.
    """

    def __init__(self, graph: NodeGraph) -> None:
        """Store the NodeGraph reference (not owned)."""
        self._graph = graph

    # --- ComponentAdapter attributes ---------------------------------------

    origin = "nodegraphqt"
    capabilities = AdapterCapabilities(
        supports_catalog=True,
        supports_selection=True,
        max_concurrent_fetch=1,
    )

    # --- ComponentAdapter methods (map 1:1 to backend verbs) --------------

    async def list_components(self, ctx: SessionContext) -> list[Component]:
        """List all nodes in the graph (verb: get_catalog)."""
        return [self._node_to_component(n) for n in self._graph.all_nodes()]

    async def get_selection(self, ctx: SessionContext) -> ComponentData:
        """Return the currently selected node(s) (verb: get_selection)."""
        selected = self._graph.selected_nodes()
        if not selected:
            return ComponentData(kind="nodegraphqt.selection", nodes=[])
        return ComponentData(
            kind="nodegraphqt.selection",
            nodes=[n.name() for n in selected],
        )

    async def get_component(self, ctx: SessionContext, component_id: str) -> Component:
        """Find a node by name (component_id == node name)."""
        node = self._find_node(component_id)
        if node is None:
            raise KeyError(f"node not found: {component_id}")
        return self._node_to_component(node)

    async def get_component_data(
        self, ctx: SessionContext, component: Component, input_args: dict[str, Any]
    ) -> ComponentData:
        """Read a node's current widget value(s) (verb: get_component_data)."""
        node = self._find_node(component.component_id)
        if node is None:
            raise KeyError(f"node not found: {component.component_id}")
        # Read the node's widget value(s) based on its type.
        class_name = type(node).__name__
        value = self._read_node_value(node, class_name)
        return ComponentData(
            kind=f"nodegraphqt.{class_name.lower()}",
            value=value,
            name=node.name(),
        )

    async def refine_component(
        self, ctx: SessionContext, component: Component, refinement: Refinement
    ) -> ComponentData:
        """Refine is not supported on the node graph (read-only adapter).

        Node properties are modified via the frontend ``update_component_in_dashboard``
        verb (a UI action), not via backend-sync ``refine_component``.
        """
        raise NotImplementedError("node graph is read-only; use update_component_in_dashboard")

    async def get_semantic_model(self, ctx: SessionContext, component: Component) -> ComponentSchema:
        """Return the node's port schema (verb: get_semantic_model)."""
        node = self._find_node(component.component_id)
        if node is None:
            raise KeyError(f"node not found: {component.component_id}")
        class_name = type(node).__name__
        schema = _NODE_PORT_SCHEMA.get(class_name, {"inputs": [], "outputs": [], "widget": None})
        return ComponentSchema(
            kind="nodegraphqt.node",
            node_type=class_name,
            inputs=schema["inputs"],
            outputs=schema["outputs"],
            widget=schema.get("widget"),
        )

    # --- Helpers (not part of the Protocol) --------------------------------

    def _find_node(self, name: str) -> BaseNode | None:
        """Find a node by its display name (component_id)."""
        for node in self._graph.all_nodes():
            if node.name() == name:
                return node
        return None

    def _node_to_component(self, node: BaseNode) -> Component:
        """Convert a NodeGraphQt node to an agentkit Component envelope."""
        return Component(
            component_id=node.name(),
            origin=self.origin,
            name=node.name(),
        )

    def _read_node_value(self, node: BaseNode, class_name: str) -> Any:
        """Read a node's widget value based on its class."""
        if class_name in ("NumberNode", "StringNode"):
            return node.get_property("value")
        # Operation nodes don't have a stored value; return their connected inputs.
        return None
