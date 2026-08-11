"""LLM factory for the examples (provider config lives here, not in runtime).

Uses langchain's ``init_chat_model`` so the provider is chosen by the model-string
prefix (``openai:...``, ``anthropic:...``, ...). For OpenRouter we use the ``openai:``
prefix (OpenRouter is OpenAI-compatible) plus the OpenRouter ``base_url``.

``agentkit-runtime`` is provider-neutral (only depends on ``langgraph`` +
``langchain-core``, takes a ``BaseChatModel``). Provider choice is the caller's concern
- this factory builds the model, reading the key from env. ``langchain`` +
``langchain-openai`` are in the workspace dev group, so no ``--with`` is needed.

Two tokens, do not confuse:
  * ``OPENROUTER_API_KEY`` (env) - LLM provider key, backend-configured.
  * ``SessionContext.auth_token`` - the user's delegated BI-fetch credential, rides the
    HTTP ``Authorization`` header, never the body (§10).
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel


__all__ = ["make_openrouter_llm"]


def make_openrouter_llm(model: str | None = None, *, streaming: bool = True) -> BaseChatModel:
    """Build a chat model via ``init_chat_model``, pointed at OpenRouter.

    OpenRouter is OpenAI-compatible, so we use the ``openai:`` prefix + the OpenRouter
    ``base_url``. The model slug is OpenRouter's (e.g. ``anthropic/claude-sonnet-4``).
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY env var not set")
    slug = model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")
    return init_chat_model(
        f"openai:{slug}",
        base_url="https://openrouter.ai/api/v1",
        api_key=key,
        streaming=streaming,
    )
