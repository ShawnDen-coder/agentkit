"""PySide6 DCC example: in-process agent, no HTTP, no SSE serialization.

Run (from repo root, after `uv sync --all-packages`):

    export OPENROUTER_API_KEY="sk-or-v1-..."
    uv run --with pyside6 --with qasync --with langchain-openai python example/pyside-dcc/app.py

This shows the LOCAL deployment (DCC host like Maya/UE/PySide): the agent runs
IN-PROCESS with the Qt UI. There is no HTTP boundary and no SSE wire serialization
- the UI consumes the ``BaseSSE`` event objects directly from
``orchestrator.run()``. The frontend FunctionCall round-trip is an in-process
re-call (``run()`` with ``role=tool``), not an HTTP disconnect + re-POST.

Contrast with ``example/fastapi-bi/``: same ``agentkit_protocol`` contracts, same
Option B state machine, two deployment modes. This is the portability claim.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path


# Make `from openrouter import make_openrouter_llm` resolve from example/_common.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_common"))

from agentkit_runtime import LanggraphOrchestrator
from dcc_adapter import MockDccAdapter
from openrouter import make_openrouter_llm
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QMainWindow
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QTextEdit
from PySide6.QtWidgets import QTreeWidget
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget
from qasync import QEventLoop

from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import Message
from agentkit_protocol import QueryRequest
from agentkit_protocol import SessionContext
from agentkit_protocol import TableArtifact
from agentkit_protocol import TextArtifact


class MainWindow(QMainWindow):
    """Chat panel + scene tree. Consumes BaseSSE events in-process."""

    def __init__(self) -> None:
        """Build the UI and wire the in-process orchestrator + DCC adapter."""
        super().__init__()
        self.setWindowTitle("agentkit · PySide6 DCC 示例")
        self.resize(900, 600)

        self._adapter = MockDccAdapter()
        self._orch = LanggraphOrchestrator(make_openrouter_llm(), self._adapter)
        self._messages: list[Message] = []
        self._tasks: set[asyncio.Task[None]] = set()  # keep refs so tasks aren't GC'd
        self._streaming = False  # True while streaming an assistant message inline

        # --- UI ---
        central = QWidget()
        layout = QVBoxLayout(central)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        layout.addWidget(self.chat, 3)

        self.scene = QTreeWidget()
        self.scene.setHeaderLabels(["场景(前端 UI 动作落在这里)"])
        layout.addWidget(self.scene, 2)

        bar = QWidget()
        bar_layout = QVBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit()
        self.input.setPlaceholderText("提问:场景里有什么")
        self.input.returnPressed.connect(self._on_send)
        self.btn = QPushButton("发送")
        self.btn.clicked.connect(self._on_send)
        bar_layout.addWidget(self.input)
        bar_layout.addWidget(self.btn)
        layout.addWidget(bar)
        self.setCentralWidget(central)

    def _on_send(self) -> None:
        """Qt slot: stash the human turn, kick off the async query on the loop."""
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._messages.append(Message(role="human", content=text))
        self._append("human", text)
        self._spawn(self._run())

    def _spawn(self, coro):
        """Schedule coro on the loop; keep a ref so it isn't garbage-collected."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self) -> None:
        """Drive the orchestrator and dispatch BaseSSE events directly (no to_sse)."""
        req = QueryRequest(
            messages=self._messages,
            session_context=SessionContext(
                user_identity="dcc-user",
                workspace_id="ws-dcc",
                trace_id="trace-dcc",
            ),
        )
        try:
            async for event in self._orch.run(req):
                if isinstance(event, CopilotMessageChunk):
                    self._stream_chunk(event.text)
                    continue
                # Non-chunk event: close any open streaming paragraph first.
                self._end_stream()
                if isinstance(event, CopilotStatusUpdate):
                    self._append("assistant", f"<i>{event.label or event.status}</i>")
                elif isinstance(event, CopilotMessageArtifact):
                    self._render_artifact(event.artifact)
                elif isinstance(event, CopilotFunctionCall):
                    # Option B in-process: execute the UI action, then re-run with role=tool.
                    self._append("assistant", f"<i>-> 前端执行:{event.name}({event.arguments})</i>")
                    self._execute_ui_action(event)
                    self._messages.append(
                        Message(role="tool", name=event.name, data={"added": True, **event.arguments})
                    )
                    self._spawn(self._run())  # resume the round-trip
                    return
                elif isinstance(event, CopilotPromptSuggestions):
                    self._append("assistant", "<i>建议:" + " · ".join(event.suggestions) + "</i>")
            self._end_stream()
        except Exception as e:  # surface orchestrator errors to the chat panel
            self._end_stream()
            self._append("assistant", f'<b style="color:#dc2626">错误:</b> {e}')

    def _stream_chunk(self, text: str) -> None:
        """Append a streamed text delta inline (not a new paragraph per chunk)."""
        if not self._streaming:
            self._append("assistant", "")  # new paragraph with the 助手 label
            self._streaming = True
        self.chat.moveCursor(QTextCursor.End)
        self.chat.insertPlainText(text)
        self.chat.ensureCursorVisible()

    def _end_stream(self) -> None:
        """Close the current streaming paragraph so the next event starts fresh."""
        self._streaming = False

    def _execute_ui_action(self, fc: CopilotFunctionCall) -> None:
        """The frontend UI action - here, add a node to the scene tree."""
        if fc.name == "add_component_to_dashboard":
            cid = fc.arguments.get("component_id", "?")
            QTreeWidgetItem(self.scene, [f"🎞  节点:{cid}"])

    def _render_artifact(self, artifact: TableArtifact | TextArtifact) -> None:
        if isinstance(artifact, TableArtifact):
            self._append("assistant", f"<b>表格</b>:{len(artifact.rows)} 行 × {len(artifact.columns)} 列")
        else:
            self._append("assistant", f"<b>文本</b>:{artifact.text}")

    def _append(self, role: str, html: str) -> None:
        label = {"human": "我", "assistant": "助手"}.get(role, role)
        color = "#2563eb" if role == "assistant" else "#888"
        self.chat.append(f'<p style="margin:4px 0;color:{color}"><b>{label}</b> {html}</p>')


def main() -> None:
    """Run the PySide6 app on a qasync asyncio loop."""
    app = QApplication(sys.argv)
    loop = QEventLoop(app)  # qasync: asyncio loop integrated with Qt's event loop
    asyncio.set_event_loop(loop)
    win = MainWindow()
    win.show()
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
