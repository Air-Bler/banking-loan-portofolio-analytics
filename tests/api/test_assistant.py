import pytest
from langchain_core.messages import AIMessage
from llm_helpers import FakeGoldRepository, ScriptedChatModel, tool_call

from api.main import app
from api.routers.assistant import get_assistant
from loan_analytics.llm import AnalyticsAssistant, ToolRegistry
from loan_analytics.llm.errors import ConfigError


def use_assistant(script, repo=None):
    """Serve /assistant from a scripted chat model and a fake Gold repository (no Azure, no Databricks)."""
    repo = repo or FakeGoldRepository().set("kpi_summary", [{"value": 0.4419}])
    app.dependency_overrides[get_assistant] = lambda: AnalyticsAssistant(ScriptedChatModel(script), ToolRegistry(repo))


@pytest.fixture
def ask(client):
    def run(script, question="What is the approval rate?"):
        use_assistant(script)
        return client.post("/assistant", json={"question": question})

    return run


def test_answer_with_evidence_and_trace(ask):
    r = ask([tool_call("get_portfolio_kpi", {"metric": "approval_rate"}), AIMessage(content="The approval rate is 44.19%.")])
    assert r.status_code == 200
    body = r.json()
    assert body["response"]["answer"] == "The approval rate is 44.19%."
    assert body["response"]["evidence"] == [{"label": "approval_rate", "value": "44.19%", "source": "kpi_portfolio_summary"}]
    assert body["response"]["source"] == ["kpi_portfolio_summary"] and body["response"]["limitations"]
    assert body["trace_id"] and [t["step"] for t in body["trace"]] == ["model_call", "tool_call", "model_call"]


def test_out_of_scope_request_is_answered_with_a_refusal_not_an_error(ask):
    r = ask([], question="Approve application LA000123")
    assert r.status_code == 200 and "can't approve" in r.json()["response"]["answer"]


def test_empty_or_oversized_question_is_422(client):
    use_assistant([])
    assert client.post("/assistant", json={"question": ""}).status_code == 422
    assert client.post("/assistant", json={"question": "x" * 1001}).status_code == 422


def test_unknown_fields_are_rejected(client):
    use_assistant([])
    assert client.post("/assistant", json={"question": "hi", "sql": "DROP TABLE x"}).status_code == 422


def test_requires_an_api_key(client):
    use_assistant([])
    assert client.post("/assistant", json={"question": "hi"}, headers={"X-API-Key": "wrong"}).status_code == 401


def test_missing_configuration_is_503_and_names_no_setting(client, monkeypatch):
    def not_configured():
        raise ConfigError("Required environment variable AZURE_OPENAI_ENDPOINT is not set.")

    monkeypatch.setattr("api.routers.assistant.create_assistant_from_env", not_configured)
    get_assistant.cache_clear()
    r = client.post("/assistant", json={"question": "What is the approval rate?"})
    assert r.status_code == 503 and "AZURE_OPENAI" not in r.text
