"""The LLM assistant. The API calls one function: answer(question, repo, llm) -> AssistantAnswer.

Raises DataUnavailable when Databricks is down and AssistantUnavailable when Azure OpenAI is down
(after the client's own retries); the API turns both into a 503 in the agreed error format.
A question that Azure's content filter blocks is not an outage: it is answered as refused.
"""

import logging
import time

import openai

from api.assistant.graph import REFUSAL, run
from api.assistant.guard import support_message
from api.assistant.schemas import AssistantAnswer
from api.errors import AssistantUnavailable

log = logging.getLogger("api.assistant")


def _filtered_categories(exc: openai.BadRequestError) -> list[str]:
    """The categories Azure's content filter blocked (self_harm, violence ...), from the error body."""
    body = exc.body if isinstance(exc.body, dict) else {}
    results = (body.get("innererror") or {}).get("content_filter_result") or {}
    return sorted(name for name, result in results.items() if isinstance(result, dict) and result.get("filtered"))


def _blocked_answer(question: str, categories: list[str], llm) -> AssistantAnswer:
    """The guard did not catch it but Azure did: the supportive message for self-harm, else the standard refusal."""
    model = getattr(llm, "deployment_name", None) or getattr(llm, "model_name", None)
    if "self_harm" in categories:
        return AssistantAnswer(status="refused", answer=support_message(question), model=model)
    return AssistantAnswer(status="refused", answer=REFUSAL, model=model,
                           limitations=["The question was blocked by the model provider's content filter."])


def answer(question: str, repo, llm) -> AssistantAnswer:
    started = time.perf_counter()
    blocked = None
    try:
        result: AssistantAnswer = run(question, repo, llm)["result"]
    except openai.BadRequestError as exc:  # a 400: Azure's content filter, or a request it could not read
        if exc.code != "content_filter":
            raise AssistantUnavailable(f"model call failed: {type(exc).__name__}") from exc
        blocked = _filtered_categories(exc)
        result = _blocked_answer(question, blocked, llm)
    except openai.OpenAIError as exc:  # timeout, 429 or 5xx after the client's retries
        raise AssistantUnavailable(f"model call failed: {type(exc).__name__}") from exc
    # Never the question, the answer or a key: each tool step (round, tool, arguments, status), rounds and duration.
    fields = {
        "status": result.status,
        "steps": result.trace,
        "tool_rounds": result.tool_rounds,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }
    if blocked is not None:
        fields["content_filter"] = blocked  # the error code's categories, never the text
    log.info("assistant answer", extra={"fields": fields})
    return result


__all__ = ["AssistantAnswer", "answer"]
