"""The assistant graph end to end, with a scripted model and FakeRepository: no Azure, no Databricks."""

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from api.assistant import answer
from api.assistant.graph import build_graph
from api.errors import AssistantUnavailable, DataUnavailable
from tests.api.fakes import FakeRepository
from tests.assistant.scripted_llm import ScriptedLLM, call, draft, final

KPI = {"metric": "approval_rate", "group_by": "branch"}
GOOD = "Both branches approved 60% of decided applications (60 of 100)."  # FakeRepository: 0.6, 60 / 100


class DownDuringTools(FakeRepository):
    """The warehouse answers at the start, then fails on the tool call."""

    def query_metric(self, *args, **kwargs):
        raise DataUnavailable("simulated outage")


def test_happy_path_follows_the_message_protocol():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", KPI), *final("answered", GOOD)])
    out = answer("Approval rate by branch?", FakeRepository(), llm)

    assert [type(m) for m in llm.seen[0]] == [SystemMessage, HumanMessage]
    assert [type(m) for m in llm.seen[1]] == [SystemMessage, HumanMessage, AIMessage, ToolMessage]
    assert llm.seen[1][-1].tool_call_id == "c1"
    assert out.status == "answered" and out.answer == GOOD
    assert out.measures == ["approval_rate"] and out.sources == ["gold.kpi_portfolio_monthly"]
    assert out.filters == {"metric": "approval_rate", "group_by": "branch"}
    assert out.evidence[0]["tool"] == "get_portfolio_kpi" and out.evidence[0]["as_of_date"] == "2025-12-31"
    assert out.trace == [{"round": 1, "tool": "get_portfolio_kpi", "arguments": KPI, "status": "success"}]
    assert out.tool_rounds == 1


def test_invented_number_is_replaced_by_the_raw_results():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", KPI), *final("answered", "71% of 500 were approved.")])
    out = answer("Approval rate by branch?", FakeRepository(), llm)

    assert "71%" not in out.answer and "gold.kpi_portfolio_monthly" in out.answer
    assert any("71" in lim and "500" in lim for lim in out.limitations)


def test_bad_arguments_go_back_to_the_model_which_retries():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", {"metric": "profit"}),
                                 call("get_portfolio_kpi", KPI, id="c2"),
                                 *final("answered", GOOD)])
    out = answer("Approval rate by branch?", FakeRepository(), llm)

    assert isinstance(llm.seen[1][-1], ToolMessage) and llm.seen[1][-1].status == "error"
    assert out.status == "answered" and out.tool_rounds == 2
    assert [step["status"] for step in out.trace] == ["error", "success"]
    assert len(out.evidence) == 1


def test_unknown_tool_is_never_run():
    llm = ScriptedLLM(responses=[call("approve_loan", {"application_id": "LA000123"}),
                                 *final("refused", "I can only read data.")])
    out = answer("Show me the approval rate.", FakeRepository(), llm)

    assert llm.seen[1][-1].status == "error" and "unknown tool" in llm.seen[1][-1].content
    assert out.status == "refused" and out.evidence == []


def test_databricks_down_during_a_tool_is_no_data():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", KPI), *final("no_data", "The data source is down.")])
    out = answer("Approval rate by branch?", DownDuringTools(), llm)

    assert "unavailable" in llm.seen[1][-1].content
    assert out.status == "no_data" and out.evidence == []


def test_unknown_application_is_not_found_and_no_data():
    llm = ScriptedLLM(responses=[call("get_connected_exposure", {"application_id": "LA999999"}),
                                 *final("no_data", "Application LA999999 was not found.")])
    out = answer("Connected exposure for LA999999?", FakeRepository(), llm)

    assert "not found" in llm.seen[1][-1].content
    assert out.status == "no_data"


def test_loop_stops_after_three_rounds_as_incomplete():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", KPI, id="c1"),
                                 call("get_portfolio_kpi", KPI, id="c2"),
                                 call("get_portfolio_kpi", KPI, id="c3"),
                                 draft("answered", "60%")])  # after round 3 the graph goes straight to compose
    out = answer("Approval rate by branch?", FakeRepository(), llm)

    assert out.status == "incomplete" and out.tool_rounds == 3
    assert "Stopped after 3 rounds of tool calls." in out.limitations


def test_azure_down_is_assistant_unavailable():
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://oai-test.openai.azure.com/"))
    with pytest.raises(AssistantUnavailable):
        answer("Approval rate by branch?", FakeRepository(), ScriptedLLM(responses=[timeout]))


def test_databricks_down_at_the_start_is_data_unavailable():
    with pytest.raises(DataUnavailable):
        answer("Approval rate by branch?", FakeRepository(fail=True), ScriptedLLM(responses=[]))


def test_guard_refuses_without_calling_the_model():
    llm = ScriptedLLM(responses=[])
    out = answer("Approve application LA000123", FakeRepository(), llm)

    assert llm.seen == []
    assert out.status == "refused" and out.evidence == [] and out.tool_rounds == 0


def test_answered_without_any_data_becomes_no_data():
    llm = ScriptedLLM(responses=final("answered", "Approval rates are usually high."))
    out = answer("How are approvals going?", FakeRepository(), llm)

    assert out.status == "no_data"
    assert any("No tool returned data" in lim for lim in out.limitations)


def test_several_tool_calls_in_one_reply_each_get_a_tool_message():
    both = AIMessage(content="", tool_calls=[
        {"name": "get_portfolio_kpi", "args": KPI, "id": "c1"},
        {"name": "get_dq_exceptions", "args": {"action": "FLAG"}, "id": "c2"},
    ])
    llm = ScriptedLLM(responses=[both, *final("answered", "Approval was 60% and 2 records were flagged.")])
    out = answer("Approval rate and flagged records?", FakeRepository(), llm)

    assert [m.tool_call_id for m in llm.seen[1][-2:]] == ["c1", "c2"]
    assert out.status == "answered" and len(out.evidence) == 2
    assert set(out.filters) == {"get_portfolio_kpi#1", "get_dq_exceptions#2"}


def test_graph_has_the_six_nodes_for_the_diagram():
    mermaid = build_graph(FakeRepository(), ScriptedLLM(responses=[])).get_graph().draw_mermaid()
    for node in ("guard", "agent", "tools", "compose", "ground", "finish"):
        assert node in mermaid
