"""Chat panel: docked QDockWidget that drives the orchestrator.

Consumes ``BaseSSE`` events in-process (no SSE serialization — this is the DCC
in-process deployment model). Node graph operations are backend-sync tools
(``build_graph``), so there's no ``CopilotFunctionCall`` interrupt/resume
round-trip — the agent↔tools loop runs multi-step within one request.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QDockWidget
from PySide6.QtWidgets import QLineEdit
from PySide6.QtWidgets import QPushButton
from PySide6.QtWidgets import QTextEdit
from PySide6.QtWidgets import QVBoxLayout
from PySide6.QtWidgets import QWidget

from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import Message
from agentkit_protocol import QueryRequest
from agentkit_protocol import SessionContext


if TYPE_CHECKING:
    from agentkit_runtime import LanggraphOrchestrator
    from PySide6.QtWidgets import QMainWindow


__all__ = ["ChatPanel"]


class ChatPanel(QDockWidget):
    """Right-docked chat panel: drives the orchestrator and streams SSE events.

    Node graph operations (``build_graph``) are backend-sync tools, so the
    chat panel just streams the response — no interrupt/resume round-trip.
    A ``thread_id`` is still generated per conversation (stateful mode for
    conversation history via the checkpointer).
    """

    def __init__(self, orchestrator: LanggraphOrchestrator, main_window: QMainWindow) -> None:
        """Build the UI and store the orchestrator + main window."""
        super().__init__("Copilot")
        self._orch = orchestrator
        self._main = main_window
        self._messages: list[Message] = []
        self._thread_id: str | None = None
        self._tasks: set[asyncio.Task] = set()
        self._streaming = False
        self._stream_interrupted = False
        self._assistant_buf = ""

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)

        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        layout.addWidget(self.chat, 3)

        self.input = QLineEdit()
        self.input.setPlaceholderText("提问:创建一套值为 50 的节点图")
        self.input.returnPressed.connect(self._on_send)
        layout.addWidget(self.input)

        self.btn = QPushButton("发送")
        self.btn.clicked.connect(self._on_send)
        layout.addWidget(self.btn)

        self.setWidget(central)
        self.setFeatures(QDockWidget.DockWidgetMovable)

    def _on_send(self) -> None:
        """Qt slot: stash the human turn, generate thread_id, kick off _run."""
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._messages.append(Message(role="human", content=text))
        self._append("human", text)
        self._thread_id = f"thread-{uuid.uuid4()}"
        self._spawn(self._run())

    def _spawn(self, coro: asyncio.coroutines) -> None:
        """Schedule coro on the asyncio loop; keep a ref so it isn't GC'd."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self) -> None:
        """Drive the orchestrator and dispatch BaseSSE events.

        Node graph operations are backend-sync (build_graph @tool), so the
        agent↔tools loop runs multi-step within this one request. No
        interrupt/resume round-trip needed.
        """
        ctx = SessionContext(
            user_identity="node-editor-user",
            workspace_id="ws-local",
            trace_id=f"trace-{uuid.uuid4()}",
        )
        req = QueryRequest(
            messages=self._messages,
            session_context=ctx,
            thread_id=self._thread_id,
        )

        self._assistant_buf = ""
        try:
            async for event in self._orch.run(req):
                if isinstance(event, CopilotMessageChunk):
                    self._stream_chunk(event.text)
                    continue
                if isinstance(event, CopilotStatusUpdate):
                    label = event.label or event.status
                    self.setWindowTitle(f"Copilot — {label}")
                    # Show thinking/tool status inline in the chat (gray italic).
                    self._end_stream()
                    self._append("status", f"<i>{label}</i>")
                    continue
                self._end_stream()
                if isinstance(event, CopilotMessageArtifact):
                    self._append("assistant", f"<i>[artifact: {type(event.artifact).__name__}]</i>")
            self._end_stream()
            self._flush_assistant()
        except Exception as e:
            self._end_stream()
            self._append("assistant", f'<b style="color:#dc2626">错误:</b> {e}')
        finally:
            self.setWindowTitle("Copilot")

    def _stream_chunk(self, text: str) -> None:
        """Append a streamed text delta inline."""
        if not self._streaming:
            self._append("assistant", "")
            self._streaming = True
        elif self._stream_interrupted:
            self.chat.moveCursor(QTextCursor.End)
            self.chat.insertPlainText("\n\n")
            self._stream_interrupted = False
            self._assistant_buf += "\n\n"
        self.chat.moveCursor(QTextCursor.End)
        self.chat.insertPlainText(text)
        self._assistant_buf += text

    def _flush_assistant(self) -> None:
        """Record the accumulated assistant text in conversation history."""
        if self._assistant_buf.strip():
            self._messages.append(Message(role="assistant", content=self._assistant_buf))
        self._assistant_buf = ""

    def _end_stream(self) -> None:
        """Close the current streaming paragraph."""
        self._streaming = False
        self._stream_interrupted = False

    def _append(self, role: str, html: str) -> None:
        """Append a paragraph to the chat log."""
        label = {"human": "我", "assistant": "助手"}.get(role, "")
        if role == "status":
            # Gray italic for thinking/tool status.
            self.chat.append(f'<p style="margin:2px 0;color:#999;font-style:italic">{html}</p>')
        else:
            color = "#2563eb" if role == "assistant" else "#888"
            self.chat.append(
                f'<p style="margin:4px 0;color:{color}"><b>{label}</b> {html}</p>'
            )
