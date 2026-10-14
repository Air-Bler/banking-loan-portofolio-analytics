"""Typed tools and run_tool: no model, no Databricks (FakeRepository from tests/api/fakes.py)."""

import json
import typing

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from api.assistant.tools import ExceptionArgs, ExposureArgs, KpiArgs, Metric, build_tools, run_tool
from api.metrics import METRICS
from tests.api.fakes import AS_OF, FakeRepository


class SpyRepository(FakeRepository):
    """FakeRepository that records which data methods were called."""

    def __init__(self, fail: bool = False):
        super().__init__(fail=fail)
        self.calls: list[str] = []

    def query_metric(self, *args, **kwargs):
        self.calls.append("query_metric")
        return super().query_metric(*args, **kwargs)

    def get_exceptions(self, *args, **kwargs):
        self.calls.append("get_exceptions")
        return super().get_exceptions(*args, **kwargs)

    def connected_exposure(self, *args, **kwargs):
        self.calls.append("connected_exposure")
        return super().connected_exposure(*args, **kwargs)


def run(repo, name, args, call_id="call_1"):
    tools = {t.name: t for t in build_tools(repo)}
    return run_tool({"name": name, "args": args, "id": call_id}, tools)


def body(message: ToolMessage) -> dict:
    return json.loads(message.content)


# ---- success -------------------------------------------------------------------------------------------------------
def test_kpi_call_succeeds_and_returns_a_run():
    repo = SpyRepository()
    message, result = run(repo, "get_portfolio_kpi", {"metric": "approval_rate", "group_by": "branch", "branch_code": "BR001"})
    assert message.status == "success" and message.tool_call_id == "call_1" and message.name == "get_portfolio_kpi"
    assert result["tool"] == "get_portfolio_kpi"
    assert result["arguments"] == {"metric": "approval_rate", "group_by": "branch", "branch_code": "BR001", "limit": 20}
    assert result["result"]["source"] == "gold.kpi_portfolio_monthly" and result["result"]["as_of_date"] == AS_OF
    assert result["result"]["filters"] == {"branch_code": "BR001"}  # only the filters that were asked for reach the repository
    assert body(message)["rows"][0]["value"] == 0.6 and repo.calls == ["query_metric"]


def test_dates_become_filters():
    _, result = run(SpyRepository(), "get_portfolio_kpi", {"metric": "applications", "date_from": "2025-01-01", "date_to": "2025-06-30"})
    assert result["result"]["filters"] == {"date_from": "2025-01-01", "date_to": "2025-06-30"}


def test_dti_band_share_for_the_whole_portfolio_is_allowed():
    message, result = run(SpyRepository(), "get_portfolio_kpi", {"metric": "dti_band_share"})
    assert message.status == "success" and {r["group"] for r in result["result"]["rows"]} == {"below_20", "20_35", "35_50", "above_50"}


def test_exceptions_filtered_by_action():
    message, result = run(SpyRepository(), "get_dq_exceptions", {"action": "REJECT"})
    assert message.status == "success" and [i["rule_id"] for i in result["result"]["items"]] == ["APP-03"]
    assert result["result"]["source"] == "gold.fact_dq_exception"


def test_metadata_lists_the_metrics_and_the_as_of_date():
    message, result = run(SpyRepository(), "get_metadata", {})
    assert message.status == "success" and result["arguments"] == {}
    assert [m["name"] for m in result["result"]["metrics"]] == list(METRICS)
    assert result["result"]["as_of_date"] == AS_OF and result["result"]["source"]


def test_connected_exposure_for_a_known_application():
    message, result = run(SpyRepository(), "get_connected_exposure", {"application_id": "LA000225"})
    assert message.status == "success" and result["result"]["members"] == 2
    assert result["result"]["total_outstanding"] == 20800.5


# ---- failures: always one error ToolMessage, never a run, never an exception ----------------------------------------
def test_unknown_metric_is_an_error_and_the_repository_is_not_called():
    repo = SpyRepository()
    message, result = run(repo, "get_portfolio_kpi", {"metric": "profit"})
    assert message.status == "error" and result is None and repo.calls == []
    assert body(message)["error"] == "invalid arguments" and body(message)["details"][0]["field"] == "metric"
    assert "profit" not in message.content  # the rejected value is not echoed back


@pytest.mark.parametrize(
    "args",
    [
        {"metric": "applications", "sql": "DROP TABLE x"},  # extra field
        {"metric": ["applications"]},  # wrong type
        {"metric": "applications", "group_by": "customer"},  # not an allowed grouping
        {"metric": "applications", "branch_code": "athens"},  # pattern
        {"metric": "applications", "limit": 51},  # above the cap
        {"metric": "applications", "limit": 0},
        {"metric": "applications", "date_from": "2025-13-45"},  # matches the pattern, not a real date
        {"metric": "applications", "date_from": "2025-06-01", "date_to": "2025-01-01"},  # reversed
        {"metric": "dti_band_share", "group_by": "branch"},  # whole portfolio only
        {"metric": "dti_band_share", "branch_code": "BR001"},
        {},  # metric is required
    ],
)
def test_invalid_kpi_arguments_are_rejected(args):
    repo = SpyRepository()
    message, result = run(repo, "get_portfolio_kpi", args)
    assert message.status == "error" and result is None and repo.calls == []
    assert body(message)["error"] == "invalid arguments"


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_dq_exceptions", {"rule_id": "XYZ-99"}),
        ("get_dq_exceptions", {"rule_id": "APP-3"}),
        ("get_dq_exceptions", {"action": "DELETE"}),
        ("get_dq_exceptions", {"limit": 500}),
        ("get_dq_exceptions", {"branch_code": "BR1"}),
        ("get_connected_exposure", {}),
        ("get_connected_exposure", {"application_id": "LA12"}),
        ("get_connected_exposure", {"application_id": "LA000225' OR 1=1 --"}),
        ("get_metadata", {"anything": 1}),
    ],
)
def test_invalid_arguments_of_other_tools_are_rejected(tool, args):
    repo = SpyRepository()
    message, result = run(repo, tool, args)
    assert message.status == "error" and result is None and repo.calls == []


def test_arguments_that_are_not_an_object():
    for raw in (None, "applications", ["applications"], 7):
        message, result = run_tool({"name": "get_portfolio_kpi", "args": raw, "id": "x"}, {t.name: t for t in build_tools(SpyRepository())})
        assert message.status == "error" and result is None and message.tool_call_id == "x"


def test_unknown_tool_is_never_run():
    repo = SpyRepository()
    message, result = run(repo, "approve_loan", {"application_id": "LA000225"}, call_id="call_9")
    assert message.status == "error" and result is None and message.tool_call_id == "call_9"
    assert body(message)["error"] == "unknown tool" and "get_portfolio_kpi" in body(message)["approved_tools"]
    assert repo.calls == []


def test_databricks_down_becomes_an_error_message():
    message, result = run(FakeRepository(fail=True), "get_portfolio_kpi", {"metric": "applications"})
    assert message.status == "error" and result is None
    assert body(message) == {"error": "data source unavailable, try again later"}


def test_unexpected_exception_does_not_leak_to_the_model():
    class Broken(FakeRepository):
        def query_metric(self, *args, **kwargs):
            raise RuntimeError("password=hunter2 in SELECT * FROM secret")

    message, result = run(Broken(), "get_portfolio_kpi", {"metric": "applications"})
    assert message.status == "error" and result is None
    assert "hunter2" not in message.content and "SELECT" not in message.content


def test_unknown_application_is_not_found():
    message, result = run(SpyRepository(), "get_connected_exposure", {"application_id": "LA999999"})
    assert message.status == "error" and result is None
    assert body(message)["error"] == "not found" and body(message)["arguments"] == {"application_id": "LA999999"}


@pytest.mark.parametrize(
    ("name", "args"),
    [
        ("get_portfolio_kpi", {"metric": "applications"}),
        ("get_portfolio_kpi", {"metric": "profit"}),
        ("get_dq_exceptions", {}),
        ("get_connected_exposure", {"application_id": "LA999999"}),
        ("execute_sql", {"sql": "SELECT 1"}),
        ("get_metadata", {"x": 1}),
    ],
)
def test_every_call_gets_exactly_one_tool_message_with_its_id(name, args):
    message, _ = run(SpyRepository(), name, args, call_id="call_abc")
    assert isinstance(message, ToolMessage) and message.tool_call_id == "call_abc"
    json.loads(message.content)  # always valid JSON, even for errors


def test_malformed_call_without_an_id_still_gets_a_message():
    message, result = run_tool({"name": "get_metadata", "args": {}}, {t.name: t for t in build_tools(SpyRepository())})
    assert isinstance(message, ToolMessage) and message.tool_call_id and result is not None


# ---- the tools themselves ---------------------------------------------------------------------------------------------------
def test_four_tools_with_forbidden_extras_and_openai_schemas():
    tools = build_tools(FakeRepository())
    assert [t.name for t in tools] == ["get_portfolio_kpi", "get_dq_exceptions", "get_metadata", "get_connected_exposure"]
    for t in tools:
        assert t.args_schema.model_config["extra"] == "forbid" and t.description
        spec = convert_to_openai_tool(t)  # what bind_tools sends to Azure OpenAI
        assert spec["function"]["name"] == t.name


def test_metric_list_matches_api_metrics():
    assert set(typing.get_args(Metric)) == set(METRICS)  # a new metric in api/metrics.py must be added to the tool


def test_limits_are_capped_at_50_rows():
    for model in (KpiArgs, ExceptionArgs):
        assert model.model_fields["limit"].metadata[1].le == 50
    assert ExposureArgs.model_fields["application_id"].metadata[0].pattern == r"^LA\d{6}$"


def test_get_metadata_is_described_for_what_can_you_do_questions():
    tool = next(t for t in build_tools(FakeRepository()) if t.name == "get_metadata")
    assert "what the assistant can answer" in " ".join(tool.description.split())


def test_descriptions_tell_the_model_what_to_do_with_unknown_metrics_and_ids():
    by_name = {t.name: " ".join(t.description.split()) for t in build_tools(FakeRepository())}
    assert "do not compute it yourself" in by_name["get_portfolio_kpi"]
    assert "do not fetch it to derive the one asked for" in by_name["get_portfolio_kpi"]  # same rule as the prompt (rule 7)
    assert "Always call it when the user names an application ID" in by_name["get_connected_exposure"]


def test_descriptions_tell_the_model_that_only_four_breakdowns_exist():
    tool = next(t for t in build_tools(FakeRepository()) if t.name == "get_portfolio_kpi")
    text = " ".join(tool.description.split())
    assert "Only four breakdowns exist: branch, product, month and year" in text
    assert "do not substitute a different breakdown" in text
    assert "No other breakdown exists" in KpiArgs.model_fields["group_by"].description
