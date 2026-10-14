import re

import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from api.assistant.llm import MAX_RETRIES, TIMEOUT_SECONDS, get_llm
from api.assistant.prompts import FINAL, PROMPT
from api.assistant.schemas import AnswerDraft, AssistantAnswer
from api.errors import AssistantUnavailable
from api.settings import Settings

CONFIGURED = {
    "azure_openai_endpoint": "https://oai-test.openai.azure.com/",
    "azure_openai_api_key": "secret-key",
    "azure_openai_deployment": "gpt-4o-mini",
}


def test_prompt_makes_a_system_and_a_human_message():
    messages = PROMPT.format_messages(question="Approval rate by branch?", as_of_date="2025-12-31",
                                      metrics="applications, approval_rate")
    assert [type(m) for m in messages] == [SystemMessage, HumanMessage]
    assert "2025-12-31" in messages[0].content and "approval_rate" in messages[0].content
    assert messages[1].content == "Approval rate by branch?"


def test_system_prompt_sets_the_guardrails():
    system = PROMPT.format_messages(question="q", as_of_date="2025-12-31", metrics="m")[0].content
    for rule in ("comes from a tool result", "cannot approve", "personal data", "Limitations"):
        assert rule in system


def test_system_prompt_sets_the_number_format_and_the_unknown_group():
    system = PROMPT.format_messages(question="q", as_of_date="2025-12-31", metrics="m")[0].content
    assert "percentages with one decimal" in system  # not 0.3841886269070735 in the answer
    assert "UNKNOWN" in system and "Leave it out of rankings" in system


def test_prompt_has_no_example_numbers_the_model_could_copy():
    # A number in the prompt (e.g. "0.3842 -> 38.4%") ends up in answers and fails the number check.
    system = PROMPT.format_messages(question="q", as_of_date="AS_OF", metrics="m")[0].content
    system = re.sub(r"^\d+\. ", "", system, flags=re.MULTILINE)  # the rule numbers 1. to 6.
    assert set(re.findall(r"\d+(?:[.,]\d+)*", system)) <= {"2016"}  # a year: the check skips years
    assert not re.search(r"\d", FINAL) and not re.search(r"\d", AnswerDraft.model_fields["answer"].description)


def test_prompt_sets_missing_metrics_differences_and_questions_about_the_assistant():
    system = PROMPT.format_messages(question="q", as_of_date="AS_OF", metrics="m")[0].content
    assert "does not exist" in system and "use status no_data" in system  # rejection rate, segment ...
    assert "difference between two values of the same metric" in system and "Never combine different metrics" in system
    assert "Breakdowns: branch, product, month and year." in system
    assert "Questions about you or what you can do: call get_metadata" in system
    assert "breakdown asked for does not exist" in FINAL


def test_answer_draft_accepts_only_the_agreed_statuses():
    assert AnswerDraft(status="answered", answer="59.2%").limitations == []
    with pytest.raises(ValidationError):
        AnswerDraft(status="maybe", answer="x")


def test_assistant_answer_defaults_are_empty():
    out = AssistantAnswer(status="refused", answer="I only read data.")
    assert out.evidence == [] and out.sources == [] and out.trace == [] and out.tool_rounds == 0


@pytest.mark.parametrize("missing", list(CONFIGURED))
def test_get_llm_without_settings_is_assistant_unavailable(missing):
    values = {**CONFIGURED, missing: ""}
    with pytest.raises(AssistantUnavailable) as exc:
        get_llm(Settings(**values))
    assert "secret-key" not in str(exc.value)


def test_get_llm_builds_a_deterministic_azure_client_without_calling_azure():
    llm = get_llm(Settings(**CONFIGURED))
    assert llm.deployment_name == "gpt-4o-mini"
    assert llm.openai_api_version == "2024-10-21"
    assert llm.temperature == 0
    assert llm.request_timeout == TIMEOUT_SECONDS and llm.max_retries == MAX_RETRIES
