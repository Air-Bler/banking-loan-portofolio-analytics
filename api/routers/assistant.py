"""POST /assistant/query: the LLM assistant (api/assistant) behind the API's auth, errors and correlation ID."""

from fastapi import APIRouter, Depends, Request
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, ConfigDict, Field

from api.assistant import AssistantAnswer, answer
from api.assistant.llm import get_llm
from api.queries import GoldRepository, get_repository

router = APIRouter(tags=["assistant"])


class AssistantQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000, examples=["What is the approval rate by branch in 2025?"])


class AssistantResponse(AssistantAnswer):
    """The assistant's structured answer (docs/contracts.md section 6) plus the request's correlation ID."""

    correlation_id: str | None = None


@router.post("/assistant/query", response_model=AssistantResponse)
def query_assistant(
    body: AssistantQuery,
    request: Request,
    repo: GoldRepository = Depends(get_repository),
    llm: BaseChatModel = Depends(get_llm),
) -> dict:
    """Ask the analytics assistant a question about the loan portfolio.

    Databricks down raises DataUnavailable and Azure OpenAI down (or not configured) raises AssistantUnavailable;
    both become a 503 in the API's error format. Anything else is unexpected and becomes a logged 500.
    """
    result = answer(body.question, repo, llm)
    return {**result.model_dump(), "correlation_id": request.state.correlation_id}
