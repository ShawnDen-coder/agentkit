r"""NodeGraphQt + AgentKit natural-language-driven node editor.

Run (from repo root):

    export OPENROUTER_API_KEY="sk-or-v1-..."
    uv run --with NodeGraphQt --with PySide6 --with qasync --with langchain-openai \
        python example/node-editor/app.py

A PySide6 ``QMainWindow`` with a NodeGraphQt graph (left) + a docked
``ChatPanel`` (right). The user types natural-language commands; the LLM
calls frontend-verb tools (``add_component_to_dashboard``, ``connect_nodes``,
...) which ``interrupt()`` the langgraph graph. ``ChatPanel`` catches the
``CopilotFunctionCall`` SSE, calls ``MainWindow._execute_fc`` to mutate the
NodeGraphQt graph, and resumes with ``thread_id + resume`` (0.3.0 stateful).
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
from node_adapter import NodeGraphQtAdapter
from NodeGraphQt import NodeGraph
from nodes import MATH_NODES
from openrouter import make_openrouter_llm
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMainWindow
from qasync import QEventLoop

from agentkit_protocol import CopilotFunctionCall


__all__ = ["MainWindow", "main"]


# System prompt teaches the LLM the component_id format + available node types.
_SYSTEM_PROMPT = """\
你是一个节点图编辑器的 copilot。用户用自然语言描述意图,你调用工具操作节点图。

可用节点类型(注册在 math.nodes 命名空间):
- NumberNode:输出一个数字。component_id 格式 "NumberNode:<value>"(如 "NumberNode:42")。
- StringNode:输出一个字符串。component_id 格式 "StringNode:<text>"(如 "StringNode:hello")。
- AddNode:加法,两个输入 a/b,输出 result。
- SubtractNode:减法,两个输入 a/b,输出 result。
- MultiplyNode:乘法,两个输入 a/b,输出 result。
- OutputNode:显示输入值(debug sink)。

操作工具:
- add_component_to_dashboard(component_id):创建节点。component_id 用上面的格式。
- update_component_in_dashboard(component_id, changes):修改节点。changes={"value": <新值>}。
- connect_nodes(source_node, target_node, source_port=0, target_port=0):连接两个节点。
  source_node/target_node 是节点名(如 "num1");端口 index 从 0 开始。

用中文回复。先调用工具执行操作,再简短解释你做了什么。
"""


class MainWindow(QMainWindow):
    """Main window: NodeGraphQt graph (central) + ChatPanel (right-docked)."""

    def __init__(self) -> None:
        """Build the UI + wire the orchestrator + adapter."""
        super().__init__()
        self.setWindowTitle("agentkit · NodeGraphQt 自然语言节点编辑器")
        self.resize(1200, 800)

        # --- NodeGraphQt graph ---
        self._graph = NodeGraph()
        self._graph.register_nodes(MATH_NODES)
        self.setCentralWidget(self._graph.widget)

        # --- AgentKit orchestrator ---
        self._adapter = NodeGraphQtAdapter(self._graph)
        self._orch = LanggraphOrchestrator(
            make_openrouter_llm(),
            self._adapter,
            system_prompt=_SYSTEM_PROMPT,
        )

        # --- Chat panel (right-docked) ---
        self._chat = ChatPanel(self._orch, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._chat)

        # Focus the chat input so the user can start typing immediately.
        self._chat.input.setFocus()

    def _execute_fc(self, fc: CopilotFunctionCall) -> str:
        """Execute a frontend UI action on the node graph.

        Called by ``ChatPanel`` when the orchestrator yields a
        ``CopilotFunctionCall`` (from ``interrupt()``). Returns a result string
        that becomes the ``resume`` payload.

        Args:
            fc: The function call from the LLM (name + arguments + tool_call_id).

        Returns:
            A result string ("created" / "updated" / "connected" / "error: ...").
        """
        try:
            if fc.name == "add_component_to_dashboard":
                return self._add_node(fc.arguments)
            if fc.name == "update_component_in_dashboard":
                return self._update_node(fc.arguments)
            if fc.name == "connect_nodes":
                return self._connect_nodes(fc.arguments)
            return f"error: unknown verb {fc.name}"
        except Exception as e:
            return f"error: {e}"

    def _add_node(self, args: dict[str, Any]) -> str:
        """Create a node from component_id format "NodeType:value"."""
        component_id = args.get("component_id", "")
        if ":" in component_id:
            node_type, value_str = component_id.split(":", 1)
        else:
            node_type, value_str = component_id, None

        # Map short name to full identifier.
        full_id = f"math.nodes.{node_type}" if not node_type.startswith("math.nodes.") else node_type
        # Generate a unique node name.
        base_name = node_type
        existing = {n.name() for n in self._graph.all_nodes()}
        name = base_name
        i = 1
        while name in existing:
            name = f"{base_name}{i}"
            i += 1

        node = self._graph.create_node(full_id, name=name)

        # Set the initial value if the node has a widget (NumberNode/StringNode).
        if value_str is not None and hasattr(node, "set_property"):
            # Try to coerce to float for NumberNode; else keep as string.
            try:
                value: float | str = float(value_str)
            except ValueError:
                value = value_str
            node.set_property("value", value)
        return "created"

    def _update_node(self, args: dict[str, Any]) -> str:
        """Modify a node's property (e.g. change its value)."""
        component_id = args.get("component_id", "")
        changes: dict = args.get("changes", {})
        node = self._find_node(component_id)
        if node is None:
            return f"error: node not found: {component_id}"
        for key, value in changes.items():
            node.set_property(key, value)
        return "updated"

    def _connect_nodes(self, args: dict[str, Any]) -> str:
        """Connect source_node.output(port) → target_node.input(port)."""
        source_name = args["source_node"]
        target_name = args["target_node"]
        source_port = int(args.get("source_port", 0))
        target_port = int(args.get("target_port", 0))

        source = self._find_node(source_name)
        target = self._find_node(target_name)
        if source is None:
            return f"error: source node not found: {source_name}"
        if target is None:
            return f"error: target node not found: {target_name}"

        source.output(source_port).connect_to(target.input(target_port))
        return "connected"

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
