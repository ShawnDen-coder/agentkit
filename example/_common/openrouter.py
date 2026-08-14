"""OpenRouter LLM factory: build a langchain ``BaseChatModel`` from env.

Reads ``OPENROUTER_API_KEY`` (required) and ``OPENROUTER_MODEL`` (optional,
defaults to ``anthropic/claude-3.5-sonnet``). Returns a ``ChatOpenAI`` pointed at
the OpenRouter OpenAI-compatible endpoint — langchain's own provider abstraction,
no wrapper layer.
"""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI


__all__ = ["make_openrouter_llm"]


def make_openrouter_llm() -> BaseChatModel:
    """Construct a langchain ``ChatOpenAI`` backed by OpenRouter.

    Raises:
        KeyError: if ``OPENROUTER_API_KEY`` is not set.
    """
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )
