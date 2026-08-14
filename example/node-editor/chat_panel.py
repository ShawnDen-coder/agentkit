"""Chat panel: docked QDockWidget that drives the orchestrator + handles HITL.

Consumes ``BaseSSE`` events in-process (no SSE serialization — this is the DCC
in-process deployment model). On ``CopilotFunctionCall`` (from ``interrupt()``),
calls ``MainWindow._execute_fc(fc)`` to mutate the node graph, then resumes with
``thread_id + resume`` (0.3.0 stateful mode).
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

from agentkit_protocol import CopilotFunctionCall
from agentkit_protocol import CopilotMessageArtifact
from agentkit_protocol import CopilotMessageChunk
from agentkit_protocol import CopilotPromptSuggestions
from agentkit_protocol import CopilotStatusUpdate
from agentkit_protocol import Message
from agentkit_protocol import QueryRequest
from agentkit_protocol import SessionContext


if TYPE_CHECKING:
    from agentkit_runtime import LanggraphOrchestrator
    from PySide6.QtWidgets import QMainWindow


__all__ = ["ChatPanel"]


class ChatPanel(QDockWidget):
    """Right-docked chat panel: drives the orchestrator + handles HITL round-trips.

    Holds a ``LanggraphOrchestrator`` + per-conversation ``thread_id``. Each new
    human turn generates a new thread_id; interrupt/resume within the same turn
    reuses it (0.3.0 stateful mode).
    """

    def __init__(self, orchestrator: LanggraphOrchestrator, main_window: QMainWindow) -> None:
        """Build the UI and store the orchestrator + main window (for _execute_fc)."""
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
        self.input.setPlaceholderText("提问:加一个值为 42 的数字节点")
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
        self._spawn(self._run(resume=None))

    def _spawn(self, coro: asyncio.coroutines) -> None:
        """Schedule coro on the asyncio loop; keep a ref so it isn't GC'd."""
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, resume: dict | None = None) -> None:
        """Drive the orchestrator and dispatch BaseSSE events.

        First call (resume=None): send messages + thread_id. On
        CopilotFunctionCall: execute the UI action via MainWindow._execute_fc,
        then re-call _run(resume={result, tool_call_id}) with the SAME thread_id.
        """
        ctx = SessionContext(
            user_identity="node-editor-user",
            workspace_id="ws-local",
            trace_id=f"trace-{uuid.uuid4()}",
        )
        if resume is not None:
            req = QueryRequest(messages=[], session_context=ctx, thread_id=self._thread_id, resume=resume)
        else:
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
                    self.setWindowTitle(f"Copilot — {event.label or event.status}")
                    if self._streaming:
                        self._stream_interrupted = True
                    continue
                self._end_stream()
                if isinstance(event, CopilotMessageArtifact):
                    self._append("assistant", f"<i>[artifact: {type(event.artifact).__name__}]</i>")
                elif isinstance(event, CopilotFunctionCall):
                    self._append(
                        "assistant",
                        f"<i>-> 执行:{event.name}({event.arguments})</i>",
                    )
                    self._assistant_buf = ""
                    result = self._main._execute_fc(event)
                    self._spawn(
                        self._run(resume={"result": result, "tool_call_id": event.tool_call_id})
                    )
                    return
                elif isinstance(event, CopilotPromptSuggestions):
                    suggestions = " · ".join(event.suggestions)
                    self._append("assistant", f"<i>建议:{suggestions}</i>")
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
        label = {"human": "我", "assistant": "助手"}.get(role, role)
        color = "#2563eb" if role == "assistant" else "#888"
        self.chat.append(
            f'<p style="margin:4px 0;color:{color}"><b>{label}</b> {html}</p>'
        )
