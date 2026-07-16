"""OpenRouter (OpenAI-compatible) client helpers."""

from __future__ import annotations

from django.conf import settings


def llm_configured() -> bool:
    return bool(settings.LLM_API_KEY)


def get_openai_client():
    """Return an OpenAI SDK client pointed at OpenRouter (or any compatible base URL)."""
    from openai import OpenAI

    default_headers = {}
    if settings.OPENROUTER_HTTP_REFERER:
        default_headers["HTTP-Referer"] = settings.OPENROUTER_HTTP_REFERER
    if settings.OPENROUTER_APP_TITLE:
        default_headers["X-Title"] = settings.OPENROUTER_APP_TITLE

    return OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        default_headers=default_headers or None,
    )
