"""The LLM assistant. The API calls one function: answer(question, repo, llm) -> AssistantAnswer.

Raises DataUnavailable when Databricks is down and AssistantUnavailable when Azure OpenAI is down
(after the client's own retries); the API turns both into a 503 in the agreed error format.
"""

import logging
import time

import openai

from api.assistant.graph import run
from api.assistant.schemas import AssistantAnswer
from api.errors import AssistantUnavailable

log = logging.getLogger("api.assistant")


def answer(question: str, repo, llm) -> AssistantAnswer:
    started = time.perf_counter()
    try:
        result: AssistantAnswer = run(question, repo, llm)["result"]
    except openai.OpenAIError as exc:  # timeout, 429 or 5xx after the client's retries
        raise AssistantUnavailable(f"model call failed: {type(exc).__name__}") from exc
    # Never the question, the answer or a key: each tool step (round, tool, arguments, status), rounds and duration.
    log.info("assistant answer", extra={"fields": {
        "status": result.status,
        "steps": result.trace,
        "tool_rounds": result.tool_rounds,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }})
    return result


__all__ = ["AssistantAnswer", "answer"]
