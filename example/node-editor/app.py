r"""NodeGraphQt + AgentKit natural-language-driven node editor.

Run (from repo root):

    export OPENROUTER_API_KEY="sk-or-v1-..."
    uv run --with NodeGraphQt --with PySide6 --with qasync --with langchain-openai \
        python example/node-editor/app.py

A PySide6 ``QMainWindow`` with a NodeGraphQt graph (left) + a docked
``ChatPanel`` (right). The user types natural-language commands; the LLM calls
``build_graph`` with a serialized graph spec (nodes + connections) which the
backend deserializes into NodeGraphQt nodes and pipes — one tool call, no
interrupt/resume round-trip.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any


# Make `from openrouter import make_openrouter_llm` resolve from example/_common.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))


from agentkit_runtime import LanggraphOrchestrator
from chat_panel import ChatPanel
from langchain_core.tools import tool
from node_adapter import NodeGraphQtAdapter
from NodeGraphQt import NodeGraph
from nodes import MATH_NODES
from openrouter import make_openrouter_llm
from pydantic import BaseModel
from pydantic import Field
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMainWindow
from qasync import QEventLoop


__all__ = ["MainWindow", "main"]


# ---------------------------------------------------------------------------
# Graph serialization schema (the structured data the LLM generates)
# ---------------------------------------------------------------------------


class NodeSpec(BaseModel):
    """A node in the serialized graph spec."""

    type: str = Field(..., description="Node type (NumberNode, AddNode, ...)")
    name: str = Field(..., description="Unique node name")
    properties: dict[str, Any] = Field(
        default_factory=dict, description='Node properties (e.g. {"value": 50} for NumberNode)'
    )


class ConnectionSpec(BaseModel):
    """A connection between two nodes' ports."""

    source: str = Field(..., description="Source node name")
    source_port: int = Field(0, description="Source node output port index")
    target: str = Field(..., description="Target node name")
    target_port: int = Field(0, description="Target node input port index")


class GraphSpec(BaseModel):
    """A complete serialized node graph: nodes + connections.

    The LLM generates this structure in one tool call; the backend deserializes
    it into NodeGraphQt nodes + pipes. This is the component serialization/
    deserialization approach — the graph is a single structured payload, not
    a sequence of individual add/connect operations.
    """

    nodes: list[NodeSpec] = Field(default_factory=list, description="Nodes to create")
    connections: list[ConnectionSpec] = Field(default_factory=list, description="Connections to make")


# ---------------------------------------------------------------------------
# System prompt: teaches the LLM the graph spec format + available node types
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """\
你是一个节点图编辑器的 copilot。用户用自然语言描述意图,你调用 build_graph 工具生成整个图的结构。

可用节点类型(math.nodes 命名空间):
- NumberNode:输出数字。properties: {"value": <number>}(如 {"value": 50})。
- StringNode:输出字符串。properties: {"value": <text>}(如 {"value": "hello"})。
- AddNode:加法,输入端口 a(0)/b(1),输出 result(0)。
- SubtractNode:减法,输入端口 a(0)/b(1),输出 result(0)。
- MultiplyNode:乘法,输入端口 a(0)/b(1),输出 result(0)。
- OutputNode:显示输入值,输入端口 value(0),无输出。

调用 build_graph(nodes=[...], connections=[...]) 一次生成整个图。
connections 里 source_port/target_port 是端口 index(从 0 开始)。

示例:用户说"加一个值为 50 的数字节点,连到加法节点再连到输出节点":
build_graph(
  nodes=[
    {"type": "NumberNode", "name": "num50", "properties": {"value": 50}},
    {"type": "AddNode", "name": "add1"},
    {"type": "OutputNode", "name": "out1"}
  ],
  connections=[
    {"source": "num50", "source_port": 0, "target": "add1", "target_port": 0},
    {"source": "add1", "source_port": 0, "target": "out1", "target_port": 0}
  ]
)

用中文回复。调用 build_graph 后简短解释你创建了什么。
"""


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Main window: NodeGraphQt graph (central) + ChatPanel (right-docked).

    The graph operations are backend-sync tools (no interrupt/resume). The LLM
    generates a GraphSpec (serialized node graph), the backend deserializes it
    into NodeGraphQt nodes + pipes in one tool call.
    """

    def __init__(self) -> None:
        """Build the UI + wire the orchestrator + adapter + build_graph tool."""
        super().__init__()
        self.setWindowTitle("agentkit · NodeGraphQt 自然语言节点编辑器")
        self.resize(1200, 800)

        # --- NodeGraphQt graph ---
        self._graph = NodeGraph()
        self._graph.register_nodes(MATH_NODES)
        self.setCentralWidget(self._graph.widget)

        # --- AgentKit orchestrator + build_graph tool ---
        self._adapter = NodeGraphQtAdapter(self._graph)
        self._orch = LanggraphOrchestrator(
            make_openrouter_llm(),
            self._adapter,
            extra_tools=[self._make_build_graph_tool()],
            system_prompt=_SYSTEM_PROMPT,
        )

        # --- Chat panel (right-docked) ---
        self._chat = ChatPanel(self._orch, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._chat)

        # Focus the chat input so the user can start typing immediately.
        self._chat.input.setFocus()

    def _make_build_graph_tool(self) -> Any:
        """Create the build_graph @tool, bound to this window's NodeGraph.

        The LLM calls this with a GraphSpec (nodes + connections). The backend
        deserializes it into NodeGraphQt nodes + pipes. This is a backend-sync
        tool — no interrupt/resume, the agent↔tools loop runs multi-step within
        one request.
        """
        graph = self._graph

        @tool
        def build_graph(
            nodes: list[NodeSpec] | None = None,
            connections: list[ConnectionSpec] | None = None,
        ) -> str:
            """Build a node graph from a serialized spec: create nodes + connect ports.

            Call this once with the full graph structure. Each node has a type
            (NumberNode, AddNode, ...), a unique name, and optional properties
            (e.g. {"value": 50}). Each connection links a source node's output
            port to a target node's input port by name + port index.
            """
            nodes = nodes or []
            connections = connections or []
            created: list[str] = []
            errors: list[str] = []

            # Phase 1: create all nodes.
            existing = {n.name() for n in graph.all_nodes()}
            name_to_node: dict[str, Any] = {}
            for spec in nodes:
                if spec.name in existing:
                    errors.append(f"node '{spec.name}' already exists")
                    continue
                full_id = f"math.nodes.{spec.type}" if not spec.type.startswith("math.") else spec.type
                try:
                    node = graph.create_node(full_id, name=spec.name)
                    for key, value in spec.properties.items():
                        node.set_property(key, value)
                    name_to_node[spec.name] = node
                    created.append(spec.name)
                except Exception as e:
                    errors.append(f"failed to create '{spec.name}': {e}")

            # Phase 2: connect ports (after all nodes exist).
            connected: list[str] = []
            for conn in connections:
                src = name_to_node.get(conn.source) or self._find_node(conn.source)
                tgt = name_to_node.get(conn.target) or self._find_node(conn.target)
                if src is None:
                    errors.append(f"connect: source '{conn.source}' not found")
                    continue
                if tgt is None:
                    errors.append(f"connect: target '{conn.target}' not found")
                    continue
                try:
                    src.output(conn.source_port).connect_to(tgt.input(conn.target_port))
                    connected.append(f"{conn.source}[{conn.source_port}]->{conn.target}[{conn.target_port}]")
                except Exception as e:
                    errors.append(f"connect {conn.source}->{conn.target}: {e}")

            # Auto-layout so the graph looks reasonable.
            graph.auto_layout_nodes()

            summary = f"created {len(created)} nodes, {len(connected)} connections"
            if errors:
                summary += f", errors: {'; '.join(errors)}"
            return summary

        return build_graph

    def _find_node(self, name: str) -> Any | None:
        """Find a node by display name."""
        for node in self._graph.all_nodes():
            if node.name() == name:
                return node
        return None


def main() -> None:
    """Run the app on a qasync asyncio loop."""
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    win = MainWindow()
    win.show()
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
