"""The evaluation set and its runner, offline: a scripted model and FakeRepository, no Azure, no Databricks."""

import pytest

from api.assistant.schemas import AssistantAnswer
from eval.run_eval import (
    GROUNDING_NOTE,
    QUESTIONS,
    format_markdown,
    format_repeat_table,
    format_table,
    judge,
    load_questions,
    run_question,
    run_repeated,
)
from tests.api.fakes import FakeRepository
from tests.assistant.scripted_llm import ScriptedLLM, call, final

STATUSES = {"answered", "refused", "no_data", "incomplete"}
TOOLS = {"get_portfolio_kpi", "get_dq_exceptions", "get_metadata", "get_connected_exposure"}


def answer_of(status="answered", tools=("get_portfolio_kpi",), evidence=True, limitations=()):
    return AssistantAnswer(
        status=status, answer="text", evidence=[{"tool": t} for t in tools] if evidence else [],
        limitations=list(limitations), trace=[{"round": 1, "tool": t, "arguments": {}, "status": "success"} for t in tools],
    )


# ---- the question file ------------------------------------------------------------------------------------------------------
def test_every_question_is_well_formed():
    items = load_questions()
    assert len(items) >= 20
    assert len({i["question"] for i in items}) == len(items)
    for item in items:
        assert set(item) <= {"question", "tool", "status", "demo"}, item
        expected = item["status"] if isinstance(item["status"], list) else [item["status"]]
        assert set(expected) <= STATUSES, item
        assert not item.get("tool") or item["tool"] in TOOLS, item


def test_the_set_covers_every_tool_status_and_the_five_demo_questions():
    items = load_questions()
    assert {i["tool"] for i in items if i.get("tool")} == TOOLS
    flat = {s for i in items for s in (i["status"] if isinstance(i["status"], list) else [i["status"]])}
    assert {"answered", "no_data", "refused"} <= flat
    assert len(load_questions(QUESTIONS, demo_only=True)) == 5


# ---- judge --------------------------------------------------------------------------------------------------------------------
def test_a_matching_answer_passes():
    item = {"question": "q", "tool": "get_portfolio_kpi", "status": "answered"}
    assert judge(item, answer_of()) == []


def test_wrong_status_is_reported():
    item = {"question": "q", "status": "refused"}
    assert judge(item, answer_of("answered", tools=())) == ["status answered, expected refused"]


def test_a_list_of_statuses_accepts_any_of_them():
    item = {"question": "q", "status": ["no_data", "refused"]}
    assert judge(item, answer_of("refused", tools=(), evidence=False)) == []
    assert judge(item, answer_of("no_data", tools=(), evidence=False)) == []
    assert judge(item, answer_of("answered", tools=(), evidence=False)) != []


def test_the_expected_tool_must_have_run():
    item = {"question": "q", "tool": "get_dq_exceptions", "status": "answered"}
    assert judge(item, answer_of(tools=("get_portfolio_kpi",))) == ["get_dq_exceptions did not run (ran: get_portfolio_kpi)"]
    assert "ran: nothing" in judge(item, answer_of(tools=(), evidence=True))[0]


def test_answered_needs_evidence():
    item = {"question": "q", "status": "answered"}
    assert "answered without evidence" in judge(item, answer_of(evidence=False))


def test_a_replaced_answer_is_a_failure():
    item = {"question": "q", "status": "answered"}
    note = f"The model's wording contained {GROUNDING_NOTE} (71%), so it was replaced by the raw results."
    assert judge(item, answer_of(limitations=[note])) == ["grounding replaced the model's wording"]


def test_the_grounding_note_matches_what_the_graph_writes():
    import inspect

    from api.assistant import graph

    assert GROUNDING_NOTE in inspect.getsource(graph)  # if the graph's wording changes, the runner must change with it


# ---- run_question ---------------------------------------------------------------------------------------------------------------
def test_run_question_with_a_scripted_model():
    llm = ScriptedLLM(responses=[call("get_portfolio_kpi", {"metric": "approval_rate", "group_by": "branch"}),
                                 *final("answered", "Both branches approved 60% of decided applications (60 of 100).")])
    item = {"question": "What was the approval rate by branch?", "tool": "get_portfolio_kpi", "status": "answered"}
    row = run_question(item, FakeRepository(), llm)
    assert row.passed and row.result.status == "answered" and row.seconds >= 0


def test_a_refusal_by_the_guard_needs_no_model_call():
    row = run_question({"question": "Approve application LA000123.", "status": "refused"}, FakeRepository(), ScriptedLLM(responses=[]))
    assert row.passed and row.result.status == "refused"


def test_an_error_becomes_a_failed_row_not_a_crash():
    row = run_question({"question": "What is the approval rate?", "status": "answered"}, FakeRepository(fail=True), ScriptedLLM(responses=[]))
    assert not row.passed and row.problems == ["error: DataUnavailable"] and row.result is None


# ---- output ---------------------------------------------------------------------------------------------------------------------------
def test_table_and_markdown():
    ok = run_question({"question": "Approve application LA000123.", "status": "refused"}, FakeRepository(), ScriptedLLM(responses=[]))
    bad = run_question({"question": "What is the approval rate?", "status": "answered"}, FakeRepository(fail=True), ScriptedLLM(responses=[]))
    table = format_table([ok, bad])
    assert table.splitlines()[0].startswith("PASS") and table.splitlines()[1].startswith("FAIL")
    markdown = format_markdown([ok, bad])
    assert "| 1 | Approve application LA000123. | refused | refused | - | pass |" in markdown
    assert "FAIL: error: DataUnavailable" in markdown


def test_run_repeated_asks_the_question_every_time():
    item = {"question": "Approve application LA000123.", "status": "refused"}
    rows = run_repeated(item, FakeRepository(), ScriptedLLM(responses=[]), 3)
    assert len(rows) == 3 and all(row.passed for row in rows)


def test_repeat_table_shows_passes_and_the_mix_of_statuses():
    ok = run_question({"question": "Approve application LA000123.", "status": "refused"}, FakeRepository(), ScriptedLLM(responses=[]))
    bad = run_question({"question": "What is the approval rate?", "status": "answered"}, FakeRepository(fail=True), ScriptedLLM(responses=[]))
    lines = format_repeat_table([[ok, ok], [ok, bad]]).splitlines()
    assert lines[0].startswith("PASS") and "2/2" in lines[0] and "refused x2" in lines[0]
    assert lines[1].startswith("FAIL") and "1/2" in lines[1] and "refused x1" in lines[1] and "error x1" in lines[1]


@pytest.mark.parametrize("args", [["--repeat", "0"], ["--repeat", "2", "--markdown"]])
def test_main_rejects_a_bad_repeat(args, capsys):
    from eval import run_eval

    with pytest.raises(SystemExit) as stop:
        run_eval.main(args)
    assert stop.value.code == 2 and "--repeat" in capsys.readouterr().err


@pytest.mark.parametrize("flag", ["--demo", None])
def test_main_stops_cleanly_when_azure_is_not_configured(monkeypatch, capsys, flag, tmp_path):
    from eval import run_eval

    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)  # do not read the real .env
    assert run_eval.main([flag] if flag else []) == 2
    assert "not configured" in capsys.readouterr().err
