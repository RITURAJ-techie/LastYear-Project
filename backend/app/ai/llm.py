"""Optional generative-AI layer (Anthropic Claude).

Every feature in InsightFlow works without it – the statistical/ML engine and
rule-based NLP produce insights and answer questions. When Anthropic
credentials are present (``ANTHROPIC_API_KEY``), Claude is used to write richer
executive narratives and to translate free-form questions into SQL.

Only aggregated findings and schema metadata (column names, types, a few
sample values) are sent to the model – never the full dataset.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from ..config import AI_DISABLED, AI_MODEL

log = logging.getLogger("insightflow.ai")


def available() -> bool:
    if AI_DISABLED:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


@lru_cache(maxsize=1)
def _client():
    import anthropic

    return anthropic.Anthropic(max_retries=2, timeout=120.0)


def complete(system: str, prompt: str, max_tokens: int = 8000, effort: str = "low") -> str | None:
    """Single-turn completion. Returns None on any failure so callers can fall back."""
    if not available():
        return None
    import anthropic

    try:
        response = _client().beta.messages.create(
            model=AI_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as exc:
        log.warning("Claude rate limited: %s", exc)
        return None
    except anthropic.APIStatusError as exc:
        log.warning("Claude API error %s: %s", exc.status_code, exc)
        return None
    except anthropic.APIConnectionError as exc:
        log.warning("Claude connection error: %s", exc)
        return None
    if response.stop_reason == "refusal":
        log.info("Claude declined the request")
        return None
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text or None
