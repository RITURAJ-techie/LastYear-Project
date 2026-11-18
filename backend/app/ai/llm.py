"""Optional generative-AI layer (Sarvam AI).

Every feature in InsightFlow works without it – the statistical/ML engine and
rule-based NLP produce insights and answer questions. When a Sarvam AI key is
present (``SARVAM_API_KEY``), Sarvam's LLM (default ``sarvam-105b``) is used to
write richer executive narratives and to translate free-form questions into SQL.

Only aggregated findings and schema metadata (column names, types, a few
sample values) are sent to the model – never the full dataset.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache

from ..config import AI_DISABLED, AI_MODEL

log = logging.getLogger("insightflow.ai")

PROVIDER = "Sarvam AI"
_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


def _api_key() -> str | None:
    return os.getenv("SARVAM_API_KEY") or os.getenv("SARVAM_API_SUBSCRIPTION_KEY")


def available() -> bool:
    if AI_DISABLED:
        return False
    return bool(_api_key())


@lru_cache(maxsize=1)
def _client():
    from sarvamai import SarvamAI

    return SarvamAI(api_subscription_key=_api_key(), timeout=120.0)


def complete(system: str, prompt: str, max_tokens: int = 8000, effort: str = "low") -> str | None:
    """Single-turn chat completion. Returns None on any failure so callers can fall back."""
    if not available():
        return None
    from sarvamai.core.api_error import ApiError

    try:
        response = _client().chat.completions(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            reasoning_effort=effort,  # none | low | medium | high | max
            max_tokens=max_tokens,
            temperature=0.2,
        )
    except ApiError as exc:
        log.warning("Sarvam API error %s: %s", exc.status_code, exc.body)
        return None
    except Exception as exc:  # noqa: BLE001 - network/timeout errors must not break analytics
        log.warning("Sarvam request failed: %s", exc)
        return None
    if not response.choices:
        return None
    choice = response.choices[0]
    if str(choice.finish_reason) == "content_filter":
        log.info("Sarvam declined the request")
        return None
    text = choice.message.content or ""
    # reasoning normally arrives in `reasoning_content`; strip inline <think> blocks defensively
    text = _THINK.sub("", text).strip()
    return text or None
