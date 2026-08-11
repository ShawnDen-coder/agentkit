"""Map agentkit ``Message`` list → langchain ``BaseMessage`` list.

Handles the orphan-``ToolMessage`` gap: the example frontends, on a frontend
``FunctionCall`` round-trip resume, append only a ``role=tool`` Message (without a
preceding ``role=assistant`` Message carrying ``tool_calls``). OpenAI/OpenRouter
reject a ``tool`` message that doesn't follow an assistant message with ``tool_calls``,
so this mapper synthesizes a minimal ``AIMessage(tool_calls=[...])`` before any orphan
``role=tool`` Message. The wire contract is unchanged (``Message.role="assistant"`` is
already in the contract — the frontends just don't send it).
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage
from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages import SystemMessage
from langchain_core.messages import ToolMessage

from agentkit_protocol import Message


__all__ = ["to_langchain_messages"]


def to_langchain_messages(messages: list[Message]) -> list[BaseMessage]:
    """Translate agentkit ``Message`` objects to langchain ``BaseMessage`` objects.

    ``role=human`` → ``HumanMessage``, ``role=assistant`` → ``AIMessage``,
    ``role=system`` → ``SystemMessage``, ``role=tool`` → ``ToolMessage``. An orphan
    ``role=tool`` Message (no preceding assistant message with ``tool_calls``) gets a
    synthesized ``AIMessage(tool_calls=[...])`` prepended so the message history is
    valid for OpenAI-format providers.
    """
    out: list[BaseMessage] = []
    for i, msg in enumerate(messages):
        if msg.role == "human":
            out.append(HumanMessage(content=msg.content or ""))
        elif msg.role == "assistant":
            out.append(AIMessage(content=msg.content or ""))
        elif msg.role == "system":
            out.append(SystemMessage(content=msg.content or ""))
        elif msg.role == "tool":
            args = msg.data or {}
            call_id = f"call_{i}"
            # Synthesize a preceding AIMessage(tool_calls=[...]) if missing.
            if not (out and isinstance(out[-1], AIMessage) and getattr(out[-1], "tool_calls", None)):
                out.append(
                    AIMessage(
                        content="",
                        tool_calls=[{"id": call_id, "name": msg.name or "", "args": args}],
                    )
                )
            out.append(ToolMessage(content=json.dumps(args), tool_call_id=call_id))
    return out
