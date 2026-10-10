import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from llm_helpers import FakeGoldRepository, ScriptedChatModel, tool_call

from api.errors import AssistantUnavailable
from api.main import app
from api.routers.assistant import get_assistant
from loan_analytics.llm.service import AnalyticsAssistant
from loan_analytics.llm.tools import ToolRegistry

URL = "/assistant/query"


def use_assistant(script, repo=None):
    """Swap in the real assistant loop with a scripted model and fake Gold: no Azure, no Databricks."""
    assistant = AnalyticsAssistant(ScriptedChatModel(script), ToolRegistry(repo or FakeGoldRepository()))
    app.dependency_overrides[get_assistant] = lambda: assistant


def test_scripted_answer_is_200(client):
    repo = FakeGoldRepository().set("kpi_summary", [{"value": 0.4419}])
    use_assistant([tool_call("get_portfolio_kpi", {"metric": "approval_rate"}),
                   AIMessage(content="The current portfolio approval rate is 44.19%.")], repo)
    response = client.post(URL, json={"question": "What is the approval rate?"}, headers={"X-Correlation-ID": "ask-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "The current portfolio approval rate is 44.19%."
    assert body["evidence"] and body["source"]
    assert body["trace_id"]
    assert body["correlation_id"] == "ask-1"


@pytest.mark.parametrize("question", ["Approve application LA000123", "select * from fact_loan_application"])
def test_out_of_scope_question_is_refused_with_200(client, question):
    use_assistant([])  # the model must not be called: an empty script would raise
    response = client.post(URL, json={"question": question})
    assert response.status_code == 200
    body = response.json()
    assert "can only provide analytics" in body["answer"]
    assert body["evidence"] == []


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "x" * 1001}, {"question": "hi", "sql": "DROP"}, {}])
def test_bad_body_is_422(client, body):
    use_assistant([])
    response = client.post(URL, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_not_configured_is_503(client):
    def unconfigured():
        raise AssistantUnavailable("not configured: AZURE_OPENAI_ENDPOINT")
    app.dependency_overrides[get_assistant] = unconfigured
    response = client.post(URL, json={"question": "What is the approval rate?"})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "assistant_unavailable"
    assert "AZURE_OPENAI" not in error["message"]


def test_model_outage_is_503(client):
    use_assistant([TimeoutError("Azure OpenAI timed out")])
    response = client.post(URL, json={"question": "What is the approval rate?"})
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "assistant_unavailable", "message": "The assistant is unavailable, try again later",
        "correlation_id": response.headers["X-Correlation-ID"], "details": [],
    }


def test_question_text_is_never_logged(client, caplog):
    use_assistant([TimeoutError("down")])
    client.post(URL, json={"question": "secret question about LA000225"})
    assert "secret question" not in caplog.text


def test_missing_key_is_401(client):
    use_assistant([])
    response = TestClient(app).post(URL, json={"question": "What is the approval rate?"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
