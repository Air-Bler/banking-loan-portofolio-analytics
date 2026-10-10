import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from loan_analytics.llm import AnalyticsAssistant, AnalyticsResponse, TraceEntry, create_assistant_from_env
from loan_analytics.llm.errors import ConfigError

log = logging.getLogger("api.assistant")
router = APIRouter(tags=["assistant"])


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"question": "What is the approval rate for risk band D?"}]})

    question: str = Field(min_length=1, max_length=1000)


class AssistantReply(BaseModel):
    """The structured answer plus the audit trail of how it was produced."""

    response: AnalyticsResponse
    trace_id: str
    trace: list[TraceEntry]


@lru_cache
def get_assistant() -> AnalyticsAssistant:
    """One assistant (graph + Azure OpenAI client + Gold repository) per process; tests swap in a fake."""
    try:
        return create_assistant_from_env()
    except ConfigError as exc:   # the message names the missing setting (never its value): log it, do not return it
        log.error("assistant not configured: %s", exc.message)
        raise HTTPException(status_code=503, detail="The assistant is not configured") from exc


@router.post("/assistant", response_model=AssistantReply)
def ask_assistant(body: AssistantRequest, assistant: AnalyticsAssistant = Depends(get_assistant)) -> AssistantReply:
    """Answer a portfolio question from approved Gold tools only. Sync on purpose: the LLM and warehouse calls block."""
    result = assistant.ask(body.question)
    return AssistantReply(response=result.response, trace_id=result.trace_id, trace=result.trace)
