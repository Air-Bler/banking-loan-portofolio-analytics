import httpx
import openai
import pytest
from fastapi.testclient import TestClient

from api.assistant.llm import get_llm
from api.main import app
from api.settings import Settings, get_settings
from tests.assistant.scripted_llm import ScriptedLLM, call, content_filter, final

URL = "/assistant/query"
QUESTION = {"question": "What is the approval rate by branch?"}
KPI = {"metric": "approval_rate", "group_by": "branch"}
GOOD = "Both branches approved 60% of decided applications (60 of 100)."  # FakeRepository: 0.6, 60 / 100


def use_llm(responses):
    """Swap in a scripted model; the client fixture already swaps in FakeRepository: no Azure, no Databricks."""
    app.dependency_overrides[get_llm] = lambda: ScriptedLLM(responses=responses)


def azure_timeout():
    return openai.APITimeoutError(request=httpx.Request("POST", "https://oai-test.openai.azure.com/"))


def test_grounded_answer_is_200(client):
    use_llm([call("get_portfolio_kpi", KPI), *final("answered", GOOD)])
    response = client.post(URL, json=QUESTION, headers={"X-Correlation-ID": "ask-1"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered" and body["answer"] == GOOD
    assert body["evidence"][0]["tool"] == "get_portfolio_kpi"
    assert body["sources"] == ["gold.kpi_portfolio_monthly"] and body["measures"] == ["approval_rate"]
    assert body["correlation_id"] == "ask-1"
    assert "trace_id" not in body


@pytest.mark.parametrize("question", ["Approve application LA000123", "select * from fact_loan_application"])
def test_out_of_scope_question_is_refused_with_200(client, question):
    use_llm([])  # the model must not be called: an empty script would fail the test
    response = client.post(URL, json={"question": question})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused"
    assert body["evidence"] == [] and body["tool_rounds"] == 0


@pytest.mark.parametrize("body", [{"question": ""}, {"question": "x" * 1001}, {"question": "hi", "sql": "DROP"}, {}])
def test_bad_body_is_422(client, body):
    use_llm([])
    response = client.post(URL, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_not_configured_is_503(client):
    # The real get_llm with empty AZURE_OPENAI_* settings (set here, so a developer's own env never leaks in).
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_env="dev", api_keys="test-key",
        azure_openai_endpoint="", azure_openai_api_key="", azure_openai_deployment="",
    )
    response = client.post(URL, json=QUESTION)
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "assistant_unavailable"
    assert "AZURE_OPENAI" not in error["message"]


def test_model_outage_is_503(client):
    use_llm([azure_timeout()])
    response = client.post(URL, json=QUESTION)
    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "assistant_unavailable", "message": "The assistant is unavailable, try again later",
        "correlation_id": response.headers["X-Correlation-ID"], "details": [],
    }


def test_content_filter_is_200_refused_not_503(client):
    use_llm([content_filter()])  # Azure blocks the prompt with a 400 content_filter
    response = client.post(URL, json={"question": "Describe a violent robbery at a branch"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused" and body["evidence"] == []


def test_databricks_down_is_503_data_unavailable(broken_client):
    use_llm([])  # Gold fails before the model is asked
    response = broken_client.post(URL, json=QUESTION)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "data_unavailable"


def test_question_text_is_never_logged(client, caplog):
    use_llm([call("get_portfolio_kpi", KPI), *final("answered", GOOD)])
    client.post(URL, json={"question": "secret question about LA000225"})
    use_llm([azure_timeout()])
    client.post(URL, json={"question": "secret question about LA000225"})
    assert "secret question" not in caplog.text


def test_missing_key_is_401(client):
    use_llm([])
    response = TestClient(app).post(URL, json=QUESTION)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
