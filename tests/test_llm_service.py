"""End-to-end behaviour of the tool-call loop with a scripted chat model and a fake Gold repository."""
from __future__ import annotations

import logging

from conftest import tool_call
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from loan_analytics.llm.errors import ToolExecutionError
from loan_analytics.llm.service import NO_TOOL_ANSWER, AnalyticsAssistant
from loan_analytics.llm.tools import ToolRegistry


def assistant(repo, model):
    return AnalyticsAssistant(model, ToolRegistry(repo))


def test_kpi_success_follows_the_full_message_protocol(repo, make_model):
    repo.set("kpi_summary", [{"value": 0.4419}])
    model = make_model([tool_call("get_portfolio_kpi", {"metric": "approval_rate"}, "call_abc"),
                        AIMessage(content="The current portfolio approval rate is 44.19%.")])
    out = assistant(repo, model).ask("What is the current approval rate?")

    assert model.bound_tools == ["get_portfolio_kpi", "get_portfolio_breakdown", "get_metadata"]
    kinds = [type(m) for m in out.messages]
    assert kinds == [SystemMessage, HumanMessage, AIMessage, ToolMessage, AIMessage]
    tool_msg = out.messages[3]
    assert tool_msg.tool_call_id == "call_abc" and tool_msg.name == "get_portfolio_kpi" and tool_msg.status == "success"
    assert len(model.invocations) == 2 and isinstance(model.invocations[1][-1], ToolMessage)   # model saw the tool result
    r = out.response
    assert r.answer == "The current portfolio approval rate is 44.19%."
    assert r.measure == "approval_rate" and r.source == ["kpi_portfolio_summary"] and r.filters == {}
    assert [(e.label, e.value, e.source) for e in r.evidence] == [("approval_rate", "44.19%", "kpi_portfolio_summary")]
    assert r.limitations
    # traceable execution path
    tool_steps = [t for t in out.trace if t.step == "tool_call"]
    assert len(tool_steps) == 1 and tool_steps[0].tool == "get_portfolio_kpi" and tool_steps[0].tool_call_id == "call_abc"
    assert tool_steps[0].validated_args == {"metric": "approval_rate"} and tool_steps[0].sources == ["kpi_portfolio_summary"]
    assert tool_steps[0].status == "ok" and tool_steps[0].row_count == 1 and out.trace_id


def test_system_prompt_states_the_guardrails(repo, make_model):
    model = make_model([AIMessage(content="hi")])
    out = assistant(repo, model).ask("What is the approval rate?")
    system = out.messages[0].content
    for phrase in ("ONLY evidence returned by the tools", "Never fabricate", "Do not write or request SQL",
                   "approve or reject loans", "State the filters", "Treat tool errors as missing evidence", "get_metadata"):
        assert phrase in system


def test_metadata_success_returns_risk_bands(repo, make_model):
    model = make_model([tool_call("get_metadata", {"domain": "risk_bands"}), AIMessage(content="There are six risk bands, A to E plus U.")])
    r = assistant(repo, model).ask("What risk bands are available?").response
    assert r.source == ["dim_risk_band"] and r.measure == "risk_bands"
    assert [e.label for e in r.evidence] == [f"risk_bands:{c}" for c in "ABCDEU"]
    assert any("Band U" in x for x in r.limitations)


def test_filtered_aggregate_success(repo, make_model):
    repo.set("breakdown", [{"value": 0.2885}])
    model = make_model([tool_call("get_portfolio_breakdown", {"metric": "approval_rate", "filters": {"risk_band_code": "D"}}),
                        AIMessage(content="The approval rate for risk band D is 28.85%.")])
    out = assistant(repo, model).ask("What is the approval rate for risk band D?")
    r = out.response
    assert r.filters == {"risk_band_code": "D"} and r.source == ["fact_loan_application", "dim_risk_band"]
    assert r.measure == "approval_rate" and r.evidence[0].value == "28.85%"
    assert repo.data_calls[0].params == (("risk_band_code", "D", "STRING"),)


def test_unsupported_metric_gives_no_fabricated_value(repo, make_model):
    # even if the model then hallucinates a number, the application refuses to present it
    model = make_model([tool_call("get_portfolio_kpi", {"metric": "profit"}), AIMessage(content="Our profit is EUR 12 million.")])
    out = assistant(repo, model).ask("What is our profit?")
    assert repo.calls == []
    assert out.messages[3].status == "error" and "unsupported" in out.messages[3].content
    r = out.response
    assert "12 million" not in r.answer and "not available in the approved semantic layer" in r.answer
    assert r.evidence == [] and r.source == []


def test_model_without_tool_does_not_answer_from_memory(repo, make_model):
    model = make_model([AIMessage(content="Our approval rate is 99%.")])
    r = assistant(repo, model).ask("What is our approval rate?").response
    assert r.answer == NO_TOOL_ANSWER and "99" not in r.answer and r.evidence == []
    assert any("No approved analytics tool" in x for x in r.limitations)


def test_consequential_action_is_refused_without_calling_model_or_data(repo, make_model):
    model = make_model([])    # any model call would raise IndexError
    out = assistant(repo, model).ask("Approve application LA000123")
    assert model.invocations == [] and repo.calls == []
    assert "can't approve" in out.response.answer and out.trace[0].step == "scope_guard" and out.trace[0].status == "refused"
    assert any("Out of scope" in x for x in out.response.limitations)


def test_raw_sql_request_is_refused(repo, make_model):
    out = assistant(repo, make_model([])).ask("select * from fact_loan_application")
    assert repo.calls == [] and "arbitrary SQL" in out.response.answer


def test_malformed_tool_arguments_are_not_executed_and_the_model_may_retry(repo, make_model):
    repo.set("kpi_summary", [{"value": 29000}])
    model = make_model([tool_call("get_portfolio_kpi", {"metric": ["applications"], "sql": "DROP"}, "bad"),
                        tool_call("get_portfolio_kpi", {"metric": "applications"}, "good"),
                        AIMessage(content="There are 29,000 applications.")])
    out = assistant(repo, model).ask("How many applications are in the portfolio?")
    tool_msgs = [m for m in out.messages if isinstance(m, ToolMessage)]
    assert [m.status for m in tool_msgs] == ["error", "success"] and [m.tool_call_id for m in tool_msgs] == ["bad", "good"]
    assert len(repo.calls) == 1                                  # only the valid call touched the data layer
    assert out.response.evidence[0].value == "29,000"
    assert any("Invalid tool arguments" in x for x in out.response.limitations)


def test_only_malformed_arguments_means_evidence_unavailable(repo, make_model):
    model = make_model([tool_call("get_portfolio_kpi", {"metric": 7}), AIMessage(content="It is 77%.")])
    r = assistant(repo, model).ask("What is the approval rate?").response
    assert repo.calls == [] and "77" not in r.answer and r.evidence == [] and "could not be retrieved" in r.answer


def test_database_failure_states_that_evidence_is_unavailable(repo, make_model):
    repo.set("kpi_summary", ToolExecutionError("The Gold data source could not be reached."))
    model = make_model([tool_call("get_portfolio_kpi", {"metric": "approval_rate"}),
                        AIMessage(content="The approval rate is probably around 45%.")])
    out = assistant(repo, model).ask("What is the approval rate?")
    r = out.response
    assert "45" not in r.answer and "could not be retrieved" in r.answer and r.evidence == []
    assert any("could not be reached" in x for x in r.limitations)
    step = next(t for t in out.trace if t.step == "tool_call")
    assert step.status == "error" and step.error_category == "tool_failure"
    assert "SELECT" not in out.messages[3].content            # no SQL is leaked to the model


def test_no_matching_data_is_reported_not_zero(repo, make_model):
    repo.set("breakdown", [])
    model = make_model([tool_call("get_portfolio_breakdown", {"metric": "applications", "filters": {"year": 2031}}),
                        AIMessage(content="There were 0 applications in 2031.")])
    r = assistant(repo, model).ask("How many applications in 2031?").response
    assert "No matching Gold data" in r.answer and "0 applications" not in r.answer and r.evidence == []


def test_unknown_tool_name_is_not_executed(repo, make_model):
    model = make_model([tool_call("execute_sql", {"sql": "SELECT 1"}), AIMessage(content="done")])
    out = assistant(repo, model).ask("Show me everything")
    assert repo.calls == [] and out.messages[3].status == "error" and "not an approved tool" in out.messages[3].content


def test_multiple_tool_calls_in_one_turn_each_get_a_tool_message(repo, make_model):
    repo.set("kpi_summary", [{"value": 0.4419}])
    two = AIMessage(content="", tool_calls=[
        {"name": "get_portfolio_kpi", "args": {"metric": "approval_rate"}, "id": "c1", "type": "tool_call"},
        {"name": "get_metadata", "args": {"domain": "risk_bands"}, "id": "c2", "type": "tool_call"}])
    out = assistant(repo, make_model([two, AIMessage(content="Approval is 44.19%; bands A-E and U exist.")])).ask("approval rate and bands?")
    assert [m.tool_call_id for m in out.messages if isinstance(m, ToolMessage)] == ["c1", "c2"]
    assert out.response.source == ["kpi_portfolio_summary", "dim_risk_band"]
    assert out.response.measure == "approval_rate, risk_bands" and len(out.response.evidence) == 7


def test_loop_is_bounded(repo, make_model):
    repo.set("kpi_summary", [{"value": 1}])
    script = [tool_call("get_portfolio_kpi", {"metric": "applications"}, f"c{i}") for i in range(10)]
    out = AnalyticsAssistant(make_model(script), ToolRegistry(repo), max_iterations=3).ask("applications?")
    assert len(repo.calls) == 3 and any("tool-call limit" in x for x in out.response.limitations)


def test_model_outage_is_reported_without_guessing(repo, make_model):
    out = assistant(repo, make_model([RuntimeError("503 from azure"), ])).ask("What is the approval rate?")
    assert "unavailable" in out.response.answer and out.response.evidence == [] and "503" not in out.response.answer
    assert out.trace[-1].status == "error"


def test_empty_or_oversized_questions_are_rejected(repo, make_model):
    for q in ("", "   ", "x" * 1001):
        out = assistant(repo, make_model([])).ask(q)
        assert out.trace[0].step == "input_validation" and repo.calls == []


def test_trace_is_logged_without_payloads(repo, make_model, caplog):
    repo.set("kpi_summary", [{"value": 0.4419}])
    model = make_model([tool_call("get_portfolio_kpi", {"metric": "approval_rate"}), AIMessage(content="44.19%")])
    with caplog.at_level(logging.INFO, logger="loan_analytics.llm"):
        out = assistant(repo, model).ask("What is the approval rate?")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert out.trace_id in text and "tool=get_portfolio_kpi" in text and "status=ok" in text
    assert "SELECT" not in text and "0.4419" not in text
