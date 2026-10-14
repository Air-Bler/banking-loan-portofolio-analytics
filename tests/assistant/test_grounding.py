"""Grounding: numbers in the answer must come from the tool results or the question. Pure code, no model."""

import pytest

from api.assistant.grounding import summarise, ungrounded_numbers
from api.assistant.tools import build_tools, run_tool
from tests.api.fakes import FakeRepository


def kpi_run(value=0.5921, numerator=244, denominator=412, group="BR003", group_by="branch"):
    return {
        "tool": "get_portfolio_kpi",
        "arguments": {"metric": "approval_rate", "group_by": group_by, "limit": 20},
        "result": {
            "metric": {"name": "approval_rate", "label": "Approval rate", "unit": "ratio", "definition": "approved / (approved + rejected)"},
            "group_by": group_by,
            "filters": {},
            "rows": [{"group": group, "value": value, "numerator": numerator, "denominator": denominator}],
            "as_of_date": "2025-12-31",
            "source": "gold.kpi_portfolio_monthly",
        },
    }


def real_runs(tool, args):
    """A run produced by the real run_tool over FakeRepository."""
    _, run = run_tool({"name": tool, "args": args, "id": "c1"}, {t.name: t for t in build_tools(FakeRepository())})
    return [run]


# ---- numbers that are grounded ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "BR003 approved 59.2% of decided applications.",
        "BR003 approved 59,2% of decided applications.",  # decimal comma
        "The approval rate is 0.59.",
        "The approval rate is 0.5921.",
        "It is 59.21% (244 of 412).",
        "It is 59 %.",
        "It is 59.2 percent.",
        "About 59% were approved.",
    ],
)
def test_a_ratio_may_be_written_as_a_rounded_ratio_or_percentage(text):
    assert ungrounded_numbers(text, "Approval rate for BR003?", [kpi_run()]) == []


def test_thousands_separators_in_any_style():
    run = {"tool": "get_portfolio_kpi", "arguments": {}, "result": {"rows": [{"group": None, "value": 1234567.0}]}}
    for text in ("There are 1,234,567 applications.", "There are 1.234.567 applications.", "There are 1234567 applications.",
                 "EUR 1,234,567.00 requested."):
        assert ungrounded_numbers(text, "How many?", [run]) == [], text


def test_european_style_number_with_decimals():
    run = {"tool": "t", "arguments": {}, "result": {"value": 1234.56}}
    assert ungrounded_numbers("Total 1.234,56 EUR and 1,234.56 EUR.", "", [run]) == []


def test_numbers_of_the_question_are_allowed():
    run = kpi_run()
    assert ungrounded_numbers("For the top 5 branches, BR003 is first.", "Show the top 5 branches by approval rate", [run]) == []
    assert ungrounded_numbers("Above 50% DTI there is nothing to report.", "What about DTI above 50%?", [run]) == []


@pytest.mark.parametrize(
    "text",
    [
        "In 2025 the approval rate was 59.2%.",
        "As of 2025-12-31 the rate is 59.2%.",
        "Data as of 31 December 2025.",
        "Data as of December 31.",
        "Για την 31η Δεκεμβρίου 2025 το ποσοστό είναι 59,2%.",
        "Between 2016 and 2024 nothing changed for 59.2%.",
        "In 2025-06 it was 59.2%.",
    ],
)
def test_years_and_dates_are_not_claims(text):
    assert ungrounded_numbers(text, "", [kpi_run()]) == []


@pytest.mark.parametrize("text", ["Branch BR003 (LA000225) broke rule APP-03 and CUS-02 in batch_001.", "Record TX0001234 and 3f9a1c0b7d2e4a51."])
def test_identifiers_are_not_numbers(text):
    assert ungrounded_numbers(text, "", [kpi_run()]) == []


def test_numbers_written_in_labels_and_definitions_are_allowed():
    run = {"tool": "get_portfolio_kpi", "arguments": {}, "result": {"metric": {"label": "30-day delinquency rate", "definition": "active loans 30 or more days past due"}, "rows": []}}
    assert ungrounded_numbers("The 30-day delinquency rate counts loans 30 days past due.", "", [run]) == []


def test_counts_of_returned_items_are_allowed():
    runs = real_runs("get_dq_exceptions", {})
    assert ungrounded_numbers("There are 3 exceptions in total.", "", runs) == []


def test_the_arguments_of_the_call_are_allowed():
    runs = real_runs("get_portfolio_kpi", {"metric": "applications", "group_by": "branch", "limit": 7})
    assert ungrounded_numbers("Showing the first 7 rows.", "", runs) == []


def test_real_tool_output_round_trip():
    runs = real_runs("get_portfolio_kpi", {"metric": "approval_rate", "group_by": "branch"})  # fake data: 0.6 = 60 of 100
    assert ungrounded_numbers("Both branches approved 60% (60 of 100).", "", runs) == []


# ---- numbers that are not --------------------------------------------------------------------------------------------------------
def test_invented_numbers_are_found():
    assert ungrounded_numbers("About 71% of 500 applications were approved.", "How many were approved?", [kpi_run()]) == ["71%", "500"]


@pytest.mark.parametrize(
    "text",
    [
        "The approval rate is 60%.",  # 59.21 rounds to 59, not 60
        "The approval rate is 0.7.",
        "The approval rate is 59.3%.",
        "There were 1.2m applications.",  # never abbreviate
        "That is 5 points higher than last year.",
        "BR003 approved 244 of 413.",
        "The approval rate is 5921.",
    ],
)
def test_wrong_or_derived_numbers_are_found(text):
    assert ungrounded_numbers(text, "", [kpi_run()]) != []


def test_each_bad_number_is_listed_once_in_order():
    assert ungrounded_numbers("71% then 500 then 71% again", "", [kpi_run()]) == ["71%", "500"]


def test_no_runs_means_every_number_is_ungrounded():
    assert ungrounded_numbers("The rate is 59.2%.", "What is the rate?", []) == ["59.2%"]


def test_text_without_numbers():
    assert ungrounded_numbers("I cannot answer that from the available data.", "", []) == []
    assert ungrounded_numbers("", "", []) == []


def test_percentage_only_converts_ratios_when_marked_as_a_percentage():
    # 0.5921 written as plain 59.2 (no % sign, no 'percent') is not accepted: the unit would be unclear
    assert ungrounded_numbers("The approval rate is 59.2.", "", [kpi_run()]) == ["59.2"]


def test_half_way_values_round_either_way():
    run = {"tool": "t", "arguments": {}, "result": {"value": 0.045}}
    assert ungrounded_numbers("It is 4.5%, about 5%.", "", [run]) == []


# ---- summarise ------------------------------------------------------------------------------------------------------------------
def test_summary_of_a_kpi_run():
    text = summarise([kpi_run()])
    assert "Approval rate" in text and "branch BR003: 59.21% (244 of 412)" in text
    assert "gold.kpi_portfolio_monthly" in text and "2025-12-31" in text


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("get_portfolio_kpi", {"metric": "approval_rate", "group_by": "branch"}),
        ("get_portfolio_kpi", {"metric": "dti_band_share"}),
        ("get_portfolio_kpi", {"metric": "applications", "group_by": "month", "date_from": "2025-11-01"}),
        ("get_dq_exceptions", {}),
        ("get_dq_exceptions", {"action": "REJECT"}),
        ("get_metadata", {}),
        ("get_connected_exposure", {"application_id": "LA000225"}),
    ],
)
def test_a_summary_is_itself_fully_grounded(tool, args):
    runs = real_runs(tool, args)
    text = summarise(runs)
    assert text and ungrounded_numbers(text, "", runs) == [], text


def test_summary_of_several_runs_and_of_nothing():
    runs = real_runs("get_portfolio_kpi", {"metric": "applications"}) + real_runs("get_dq_exceptions", {})
    text = summarise(runs)
    assert text.count("Source:") == 2
    assert summarise([]) == "No data was retrieved."


def test_summary_of_an_unknown_tool_does_not_fail():
    assert "Source: unknown" in summarise([{"tool": "other", "arguments": {}, "result": {"x": 1}}])


def test_summary_formats_amounts_and_counts():
    run = {"tool": "get_portfolio_kpi", "arguments": {}, "result": {
        "metric": {"label": "Outstanding balance", "unit": "EUR", "definition": "outstanding principal"},
        "group_by": None, "filters": {"branch_code": "BR001"},
        "rows": [{"group": None, "value": 129992400.62}], "as_of_date": "2025-12-31", "source": "gold.kpi_portfolio_monthly"}}
    text = summarise([run])
    assert "EUR 129,992,400.62" in text and "Filters: branch_code=BR001" in text and "- branch BR001: EUR 129,992,400.62" in text
    assert "Whole portfolio" not in text
    assert ungrounded_numbers(text, "", [run]) == []


def test_summary_says_whole_portfolio_when_only_dates_are_filtered():
    run = {"tool": "get_portfolio_kpi", "arguments": {}, "result": {
        "metric": {"label": "Applications", "unit": "count", "definition": "number of loan applications"},
        "group_by": None, "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"},
        "rows": [{"group": None, "value": 12000}], "as_of_date": "2025-12-31", "source": "gold.kpi_portfolio_monthly"}}
    text = summarise([run])
    assert "- Whole portfolio: 12,000" in text and "branch" not in text.lower().replace("branch_code", "")
    assert ungrounded_numbers(text, "", [run]) == []


# ---- numbers written in field names (found by the evaluation on the real model) ---------------------------------------------
def test_a_threshold_written_in_a_field_name_is_allowed():
    # connected_exposure has is_delinquent_30 per application; "30+ days past due" is its definition, not a new figure
    run = {"tool": "get_connected_exposure", "arguments": {"application_id": "LA000225"},
           "result": {"members": 2, "delinquent_loans": 0, "applications": [{"application_id": "LA000225", "is_delinquent_30": 0}]}}
    text = "The household has 2 borrowers and no loans 30 or more days past due."
    assert ungrounded_numbers(text, "What is the connected exposure for application LA000225?", [run]) == []


def test_a_metric_name_with_a_number_allows_that_number():
    run = {"tool": "get_portfolio_kpi", "arguments": {"metric": "delinquency_rate_30"}, "result": {"rows": []}}
    assert ungrounded_numbers("Loans 30 days past due.", "", [run]) == []


def test_other_numbers_are_still_found_next_to_such_names():
    run = {"tool": "t", "arguments": {}, "result": {"is_delinquent_30": 0, "as_of_date": "2025-12-31", "source": "gold.kg_nodes"}}
    assert ungrounded_numbers("About 45 days, in 12 branches, 31%.", "", [run]) == ["45", "12", "31%"]  # date parts are not allowed


def test_identifiers_with_letters_before_the_number_do_not_allow_it():
    run = {"tool": "t", "arguments": {"branch_code": "BR003"}, "result": {"group": "LA000225", "batch": "batch_001"}}
    assert ungrounded_numbers("Exactly 3 branches.", "", [run]) == ["3"]



def test_a_percentage_in_the_question_may_come_back_as_a_fraction():
    # "Compare the approval rate with a target of 70%": the model wrote 0.7 (found by the team's tests with the real model)
    question = "Compare the approval rate with a target of 70%"
    assert ungrounded_numbers("The rate of 0.5921 is below your target of 0.7.", question, [kpi_run()]) == []
    assert ungrounded_numbers("The rate of 0.5921 is below your target of 70%.", question, [kpi_run()]) == []
    assert ungrounded_numbers("The rate is below your target of 0.8.", question, [kpi_run()]) == ["0.8"]


# ---- the difference of two values of one KPI ------------------------------------------------------------------------------------
def kpi_rows(metric, unit, rows, group_by="branch", filters=None):
    """A KPI run with several rows: rows is [(group, value), ...]."""
    return {
        "tool": "get_portfolio_kpi",
        "arguments": {"metric": metric, "group_by": group_by},
        "result": {
            "metric": {"name": metric, "label": metric, "unit": unit, "definition": "d"},
            "group_by": group_by,
            "filters": filters or {},
            "rows": [{"group": group, "value": value} for group, value in rows],
            "as_of_date": "2025-12-31",
            "source": "gold.kpi_portfolio_monthly",
        },
    }


DELINQUENCY = kpi_rows("delinquency_rate_30", "ratio", [("BR001", 0.1183), ("BR002", 0.1277), ("BR003", 0.1229)])


@pytest.mark.parametrize(
    "text",
    [
        "BR001 is at 11.8% and BR002 at 12.8%, a difference of 1.0 percentage points.",  # from the rounded figures
        "BR001 is at 11.83% and BR002 at 12.77%: 0.94 points apart.",  # from the exact ones
        "BR001 has 11.8% and BR002 has 12.8%, so BR002 is 0.9 points higher.",  # exact 0.94 rounded
    ],
)
def test_a_difference_of_two_shown_values_of_one_kpi_is_allowed(text):
    assert ungrounded_numbers(text, "", [DELINQUENCY]) == []


def test_the_two_values_may_come_from_two_runs():
    runs = [
        kpi_rows("approval_rate", "ratio", [("BR003", 0.4549)], group_by=None, filters={"branch_code": "BR003"}),
        kpi_rows("approval_rate", "ratio", [("BR012", 0.426)], group_by=None, filters={"branch_code": "BR012"}),
    ]
    assert ungrounded_numbers("BR003 approved 45.5% and BR012 42.6%: 2.9 points more.", "", runs) == []


def test_an_amount_difference_of_one_kpi_is_allowed():
    run = kpi_rows("outstanding_balance", "EUR", [("BR001", 1000000.5), ("BR002", 800000.5)])
    assert ungrounded_numbers("BR001 has 1,000,000.5 and BR002 800,000.5: 200,000 apart.", "", [run]) == []


@pytest.mark.parametrize(
    "text",
    [
        "BR003 is 2.9 points above BR012.",  # the two values are not shown, so the figure cannot be checked
        "BR001 is at 11.8% and BR002 at 12.8%, a difference of 4.0 points.",  # not their difference
        "BR002 is 1.1 times BR001: 12.8% against 11.8%.",  # a ratio is not a difference
        "BR001 is at 11.8%, so 88.2% of the loans are not delinquent.",  # 1 minus a rate
    ],
)
def test_anything_else_is_still_an_invented_figure(text):
    assert ungrounded_numbers(text, "", [DELINQUENCY]) != []


def test_a_difference_of_two_different_kpis_is_not_allowed():
    runs = [
        kpi_rows("delinquency_rate_30", "ratio", [("BR001", 0.1183)]),
        kpi_rows("approval_rate", "ratio", [("BR001", 0.4489)]),
    ]
    text = "Delinquency is 11.8% and approval 44.9%: 33.1 points apart."
    assert ungrounded_numbers(text, "", runs) == ["33.1"]


def test_a_difference_of_a_value_and_a_constant_is_not_allowed():
    run = kpi_rows("approval_rate", "ratio", [("BR001", 0.4489)])
    assert ungrounded_numbers("BR001 approves 44.9%, which is 5.1 points under 50%.", "", [run]) != []
