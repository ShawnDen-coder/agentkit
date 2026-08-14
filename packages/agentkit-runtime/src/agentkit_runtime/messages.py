"""Message conversion: agentkit ``Message`` → langchain ``BaseMessage``.

0.3.0: uses langchain's native ``convert_to_messages`` for the standard mapping.
The orphan-``ToolMessage`` synthesis (M2) is retained only for 0.2.0-style
``role=tool`` messages without ``tool_call_id`` — 0.3.0 messages that carry
``tool_call_id`` go through ``convert_to_messages`` directly.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.messages import BaseMessage
from langchain_core.messages import ToolMessage
from langchain_core.messages import convert_to_messages

from agentkit_protocol import Message


__all__ = ["to_langchain_messages"]


def to_langchain_messages(messages: list[Message]) -> list[BaseMessage]:
    """Translate agentkit ``Message`` objects to langchain ``BaseMessage`` objects.

    Uses langchain's native ``convert_to_messages`` for messages with
    ``tool_call_id`` (0.3.0+). For 0.2.0-style orphan ``role=tool`` messages
    (no ``tool_call_id``), synthesizes a preceding ``AIMessage(tool_calls=[...])``
    so the message history is valid for OpenAI-format providers.
    """
    out: list[BaseMessage] = []
    for i, msg in enumerate(messages):
        if msg.role == "tool" and not msg.tool_call_id:
            # 0.2.0 backward-compat: orphan role=tool without tool_call_id.
            args = msg.data or {}
            call_id = f"call_{i}"
            if not (out and isinstance(out[-1], AIMessage) and getattr(out[-1], "tool_calls", None)):
                out.append(
                    AIMessage(
                        content="",
                        tool_calls=[{"id": call_id, "name": msg.name or "", "args": args}],
                    )
                )
            out.append(ToolMessage(content=str(msg.data or ""), tool_call_id=call_id))
        else:
            out.append(convert_to_messages([msg.model_dump()])[0])
    return out
