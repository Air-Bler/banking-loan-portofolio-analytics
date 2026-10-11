"""What the model writes (AnswerDraft) and what the API returns (AssistantAnswer).

Only status, answer and limitations come from the model. evidence, filters, sources, measures and trace are
built by code from the tool calls that actually ran, so the model cannot invent them.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["answered", "refused", "no_data", "incomplete"]


class AnswerDraft(BaseModel):
    """The final answer to the user's question, written only from the tool results in this conversation."""

    status: Status = Field(
        description="answered: the tools returned data and the answer uses it; refused: out of scope, an action "
        "or personal data; no_data: the tools returned nothing usable; incomplete: the answer is partial."
    )
    answer: str = Field(description="2-4 sentences in the language of the question. Every number comes from a tool result.")
    limitations: list[str] = Field(
        default_factory=list, description="What the answer does not cover: date range, missing data, failed tools."
    )


class AssistantAnswer(BaseModel):
    """The structured answer of POST /assistant/query."""

    status: Status
    answer: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)  # one entry per successful tool call
    filters: dict[str, Any] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    measures: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)  # every tool call, failed ones included
    model: str | None = None
    tool_rounds: int = 0
