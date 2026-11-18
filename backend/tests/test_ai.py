"""Sarvam AI integration: request shape, output cleaning and graceful fallback (SDK mocked)."""
from types import SimpleNamespace

import pytest

from app.ai import llm


class FakeChat:
    def __init__(self, content, finish="stop", exc=None):
        self.content, self.finish, self.exc, self.calls = content, finish, exc, []

    def completions(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        msg = SimpleNamespace(content=self.content, reasoning_content="hidden reasoning")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish)])


@pytest.fixture
def fake(monkeypatch):
    def install(**kw):
        chat = FakeChat(**kw)
        monkeypatch.setattr(llm, "AI_DISABLED", False)
        monkeypatch.setenv("SARVAM_API_KEY", "test-key")
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=chat))
        return chat
    return install


def test_request_shape_and_think_stripping(fake):
    chat = fake(content="<think>scratch work</think>\n**Revenue grew 12%.**")
    out = llm.complete("system prompt", "user prompt", max_tokens=500, effort="medium")
    assert out == "**Revenue grew 12%.**"
    call = chat.calls[0]
    assert call["model"] == llm.AI_MODEL
    assert call["messages"][0] == {"role": "system", "content": "system prompt"}
    assert call["messages"][1] == {"role": "user", "content": "user prompt"}
    assert call["reasoning_effort"] == "medium" and call["max_tokens"] == 500


def test_api_error_falls_back(fake):
    from sarvamai.core.api_error import ApiError

    fake(content=None, exc=ApiError(status_code=403, body={"error": "invalid key"}))
    assert llm.complete("s", "p") is None


def test_content_filter_falls_back(fake):
    fake(content="", finish="content_filter")
    assert llm.complete("s", "p") is None


def test_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(llm, "AI_DISABLED", False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    monkeypatch.delenv("SARVAM_API_SUBSCRIPTION_KEY", raising=False)
    assert not llm.available() and llm.complete("s", "p") is None


def test_nlq_uses_sarvam_sql(fake, client, auth):
    """End-to-end: an AI-generated SQL plan is validated, executed and narrated."""
    from conftest import make_sales_csv

    r = client.post("/api/datasets/upload", headers=auth, files={"file": ("ai.csv", make_sales_csv(), "text/csv")}, data={"name": "AI Test"})
    ds = r.json()[0]["dataset"]
    plan = ('{"sql": "SELECT \\"region\\", sum(\\"revenue\\") AS total_revenue FROM ' + ds["table_name"] +
            ' GROUP BY 1 ORDER BY 2 DESC", "chart": "bar", "x": "region", "y": ["total_revenue"], "explanation": "Revenue per region"}')
    chat = fake(content=plan)
    body = client.post("/api/ai/ask", headers=auth, json={"dataset_id": ds["id"], "question": "which region sells most?"}).json()
    assert body["mode"] == "ai" and body["result"]["x"] == "region" and len(body["result"]["rows"]) == 4
    assert len(chat.calls) == 2  # SQL generation + narrated answer

    # a malicious plan is rejected by the SQL guard and the rules engine answers instead
    fake(content='{"sql": "DROP TABLE ' + ds["table_name"] + '", "chart": "table"}')
    body = client.post("/api/ai/ask", headers=auth, json={"dataset_id": ds["id"], "question": "total revenue by region"}).json()
    assert body["mode"] == "rules"
