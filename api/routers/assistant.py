"""POST /assistant/query: the LLM pair's AnalyticsAssistant behind the API's auth, errors and correlation ID."""

import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from api.errors import AssistantUnavailable
from loan_analytics.llm.errors import ConfigError
from loan_analytics.llm.models import AnalyticsResponse as AssistantAnswer
from loan_analytics.llm.service import AnalyticsAssistant, create_assistant_from_env

log = logging.getLogger("api.assistant")
router = APIRouter(tags=["assistant"])


class AssistantQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000, examples=["What is the approval rate by branch in 2025?"])


class AssistantResponse(AssistantAnswer):
    """The assistant's structured answer (answer, evidence, filters, source, measure, limitations) plus IDs."""

    trace_id: str
    correlation_id: str | None = None


@lru_cache
def _build_assistant() -> AnalyticsAssistant:
    # lru_cache never stores an exception, so a ConfigError is retried on the next request.
    return create_assistant_from_env()


def get_assistant() -> AnalyticsAssistant:
    """FastAPI dependency; tests swap in an assistant with a scripted model and a fake repository."""
    try:
        return _build_assistant()
    except ConfigError as exc:
        # ConfigError names the missing setting, never its value.
        raise AssistantUnavailable(f"not configured: {exc.message}") from exc


@router.post("/assistant/query", response_model=AssistantResponse)
def query_assistant(
    body: AssistantQuery, request: Request, assistant: AnalyticsAssistant = Depends(get_assistant)
) -> dict:
    """Ask the analytics assistant a question about the loan portfolio."""
    try:
        result = assistant.ask(body.question)
    except Exception as exc:
        raise AssistantUnavailable(f"ask failed: {type(exc).__name__}") from exc
    # ask() catches a failed model call itself and answers "unavailable"; the API reports that as 503.
    failed = next((t for t in result.trace if t.step == "model_call" and t.status == "error"), None)
    if failed:
        raise AssistantUnavailable(f"model call failed: {failed.error_category}")
    return {
        **result.response.model_dump(),
        "trace_id": result.trace_id,
        "correlation_id": request.state.correlation_id,
    }
