"""ScriptedLLM: a fake chat model that replays the replies a test scripts, in order. No network, no Azure.

LangChain's own fake chat models don't support bind_tools, so this subclass adds it. A scripted exception is
raised instead of returned (to simulate an Azure outage), and running out of replies fails the test loudly.
"""

from typing import Any

import httpx
import openai
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field


class ScriptedLLM(FakeMessagesListChatModel):
    responses: list[Any]  # AIMessages, or exceptions to raise
    seen: list = Field(default_factory=list)  # the messages sent on each call

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self.seen.append(list(messages))
        if self.i >= len(self.responses):
            raise AssertionError(f"ScriptedLLM was called {self.i + 1} times but only has {len(self.responses)} replies")
        reply = self.responses[self.i]
        self.i += 1
        if isinstance(reply, BaseException):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])


def call(name: str, args: dict, id: str = "c1") -> AIMessage:
    """The model asks for one tool."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def draft(status: str, answer: str, limitations=()) -> AIMessage:
    """with_structured_output(AnswerDraft) is a forced AnswerDraft tool call."""
    return call("AnswerDraft", {"status": status, "answer": answer, "limitations": list(limitations)}, id="final")


def final(status: str, answer: str, limitations=()) -> list[AIMessage]:
    """The model's last text reply (no tool calls), then its structured answer."""
    return [AIMessage(content=answer), draft(status, answer, limitations)]


def content_filter(category: str = "violence") -> openai.BadRequestError:
    """The 400 Azure OpenAI returns when its content filter blocks a prompt, as the openai client raises it."""
    body = {"code": "content_filter", "message": "The prompt was filtered.",
            "innererror": {"code": "ResponsibleAIPolicyViolation",
                           "content_filter_result": {category: {"filtered": True, "severity": "medium"}}}}
    response = httpx.Response(400, request=httpx.Request("POST", "https://oai-test.openai.azure.com/"))
    return openai.BadRequestError("The prompt was filtered.", response=response, body=body)
