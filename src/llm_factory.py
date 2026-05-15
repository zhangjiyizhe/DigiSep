# src/llm_factory.py
#
# Central LLM factory — single place to control which provider and model
# is used by Agent 1, Agent 2, and Agent 4.
#
# HOW TO SWITCH MODELS:
#   1. Open config.py
#   2. Set LLM_PROVIDER = "groq"   (or "anthropic" to go back)
#   3. Set GROQ_MODEL   = "llama-3.3-70b-versatile"   (or any Groq model)
#   No other file needs to change.
#
# Supported providers:
#   "anthropic" — ChatAnthropic (original)
#   "groq"      — ChatGroq via langchain-groq (new)

from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from config import LLM_PROVIDER, ANTHROPIC_MODEL, GROQ_MODEL, MAX_OUTPUT_TOKENS


def get_llm(temperature: float = 0.0, max_tokens: int | None = None):
    """
    Return a configured LangChain chat model for the active provider.

    Args:
        temperature: Sampling temperature (0.0 = deterministic).
        max_tokens:  Max output tokens. If None, uses MAX_OUTPUT_TOKENS from config.

    Returns:
        A LangChain BaseChatModel instance (ChatAnthropic or ChatGroq).

    Raises:
        ValueError: If LLM_PROVIDER in config.py is not recognised.
        ImportError: If the required package for the chosen provider is not installed.
    """
    tokens = max_tokens if max_tokens is not None else MAX_OUTPUT_TOKENS

    if LLM_PROVIDER == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as e:
            raise ImportError(
                "langchain-anthropic is not installed. "
                "Run: pip install langchain-anthropic"
            ) from e

        return ChatAnthropic(
            model=ANTHROPIC_MODEL,
            temperature=temperature,
            max_tokens=tokens,
        )

    elif LLM_PROVIDER == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as e:
            raise ImportError(
                "langchain-groq is not installed. "
                "Run: pip install langchain-groq"
            ) from e

        return ChatGroq(
            model=GROQ_MODEL,
            temperature=temperature,
            max_tokens=tokens,
        )

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{LLM_PROVIDER}' in config.py. "
            "Valid options: 'anthropic', 'groq'."
        )