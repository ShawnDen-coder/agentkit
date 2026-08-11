"""Minimal langgraph + OpenRouter connectivity test (no agentkit, no tools).

Isolates one thing: can langgraph drive a chat model (built via ``init_chat_model``)
pointed at OpenRouter and stream a reply? If this works, the connection is fine and
any 404 is a model tool-use issue, not a connectivity issue.

Run (deps are in the workspace dev group, so no ``--with``):

    export OPENROUTER_API_KEY="<your-key>"
    export OPENROUTER_MODEL="anthropic/claude-sonnet-4"
    uv run --all-packages --env-file .env python example/_common/test_langgraph.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Annotated
from typing import TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages


def _make_llm() -> BaseChatModel:
    """Build a chat model via ``init_chat_model``, pointed at OpenRouter."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    slug = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    print(f"[setup] model=openai:{slug}  base=openrouter  key=...{key[-4:]}")
    return init_chat_model(
        f"openai:{slug}",
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        streaming=True,
    )


class _State(TypedDict):
    """langgraph state: a message list with the ``add_messages`` reducer."""

    messages: Annotated[list, add_messages]


async def main() -> None:
    """Run a one-node graph that calls the LLM and streams the reply."""
    llm = _make_llm()

    async def agent(state: _State) -> dict:
        """One node: invoke the LLM on the message list."""
        ai = await llm.ainvoke(state["messages"])
        return {"messages": [ai]}

    graph = StateGraph(_State)
    graph.add_node("agent", agent)
    graph.add_edge(START, "agent")
    app = graph.compile()

    print("\n[stream] 用一句话介绍你自己")
    async for ev in app.astream_events(
        {"messages": [HumanMessage(content="用一句话介绍你自己")]},
        version="v2",
    ):
        if ev["event"] == "on_chat_model_stream":
            chunk = ev["data"].get("chunk")
            text = getattr(chunk, "content", "") if chunk else ""
            if isinstance(text, str) and text:
                print(text, end="", flush=True)
    print("\n\n[ok] langgraph <-> OpenRouter 通信成功")


if __name__ == "__main__":
    asyncio.run(main())
