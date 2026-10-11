"""The assistant as a LangGraph StateGraph with hand-written nodes.

    START -> guard --(refused)--------------------------------------------> finish -> END
               |
               v
             agent --(tool calls, rounds < 3)--> tools --> agent
               |                                   |
               | (no tool calls)                   | (3 rounds: incomplete)
               v                                   v
             compose <-----------------------------+
               v
             ground -> finish -> END

No prebuilt agent (create_react_agent, ToolNode): the brief grades detecting tool calls, validating them, running
them and returning ToolMessages, so those steps stay visible here and in tools.run_tool. Inside the nodes we use
plain LangChain Core: ChatPromptTemplate, bind_tools, ToolMessage and with_structured_output.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from api.assistant.grounding import summarise, ungrounded_numbers
from api.assistant.guard import check_question
from api.assistant.prompts import FINAL, PROMPT
from api.assistant.schemas import AnswerDraft, AssistantAnswer
from api.assistant.tools import build_tools, run_tool

MAX_ROUNDS = 3
REFUSAL = (
    "I can only answer questions about the loan portfolio from the governed Gold data. I can't approve, change or "
    "delete anything, run SQL, or give personal data."
)


class AssistantState(TypedDict, total=False):
    """What the nodes share for one question. Lists with operator.add are appended to, never overwritten."""

    question: str
    messages: Annotated[list[AnyMessage], add_messages]  # system, human, AI and tool messages
    runs: Annotated[list[dict], operator.add]  # successful tool calls: the evidence
    trace: Annotated[list[dict], operator.add]  # every tool call, failed ones included
    limitations: Annotated[list[str], operator.add]
    rounds: int
    status: str | None  # set by code (refused, incomplete) or by compose
    answer: str
    result: AssistantAnswer


def _unique(items) -> list:
    return list(dict.fromkeys(item for item in items if item))


def build_graph(repo, llm):
    """One compiled graph per request, around this request's repository and model."""
    tools = build_tools(repo)
    by_name = {t.name: t for t in tools}
    model_with_tools = llm.bind_tools(tools)

    # ---- nodes -----------------------------------------------------------------------------------------------
    def guard(state: AssistantState) -> dict:
        """Refuse actions, SQL, personal data and prompt injection before the model sees the question."""
        reason = check_question(state["question"])
        if reason:
            return {"status": "refused", "answer": REFUSAL,
                    "limitations": [f"Refused before any data was read ({reason})."]}
        return {}

    def agent(state: AssistantState) -> dict:
        """The model reads the conversation and either asks for tools or stops."""
        new = []
        if not state.get("messages"):  # first turn: system + human messages from the template
            info = repo.refresh_info()
            metrics = ", ".join(m["name"] for m in repo.metric_catalogue())
            new = PROMPT.format_messages(question=state["question"], as_of_date=info["as_of_date"], metrics=metrics)
        reply = model_with_tools.invoke([*state.get("messages", []), *new])
        return {"messages": [*new, reply]}

    def tools_node(state: AssistantState) -> dict:
        """Run every tool call of the last AI message; each one gets exactly one ToolMessage."""
        rounds = state.get("rounds", 0) + 1
        messages, runs, trace = [], [], []
        for call in state["messages"][-1].tool_calls:
            tool_message, run = run_tool(call, by_name)
            messages.append(tool_message)
            trace.append({"round": rounds, "tool": call["name"], "arguments": call.get("args"),
                          "status": tool_message.status})
            if run:
                runs.append(run)
        update = {"messages": messages, "runs": runs, "trace": trace, "rounds": rounds}
        if rounds >= MAX_ROUNDS:
            update |= {"status": "incomplete", "limitations": [f"Stopped after {MAX_ROUNDS} rounds of tool calls."]}
        return update

    def compose(state: AssistantState) -> dict:
        """The model writes status, answer and limitations as an AnswerDraft, from the tool results only."""
        writer = llm.with_structured_output(AnswerDraft, method="function_calling")
        draft = writer.invoke([*state["messages"], HumanMessage(FINAL)])
        if draft is None:  # the model ignored the forced structured call
            draft = AnswerDraft(status="no_data", answer=summarise(state.get("runs", [])),
                                limitations=["The model did not return a structured answer."])
        status = state.get("status") or draft.status
        limitations = list(draft.limitations)
        if status == "answered" and not state.get("runs"):  # an answer with no data behind it
            status = "no_data"
            limitations.append("No tool returned data, so the answer is not based on the governed data.")
        return {"status": status, "answer": draft.answer, "limitations": limitations}

    def ground(state: AssistantState) -> dict:
        """Every number in the answer must come from a tool result or the question; otherwise show the raw results."""
        runs = state.get("runs", [])
        bad = ungrounded_numbers(state["answer"], state["question"], runs)
        if not bad:
            return {}
        return {"answer": summarise(runs),
                "limitations": [f"The model's wording contained numbers not found in the data ({', '.join(bad)}), "
                                "so it was replaced by the raw results."]}

    def finish(state: AssistantState) -> dict:
        """Build the AssistantAnswer: evidence, filters, sources and measures come from the runs, never the model."""
        runs = state.get("runs", [])
        evidence = [{"tool": r["tool"], "arguments": r["arguments"], "source": r["result"].get("source"),
                     "as_of_date": r["result"].get("as_of_date"), "result": r["result"]} for r in runs]
        filters_per_run = [{k: v for k, v in r["arguments"].items() if k != "limit"} for r in runs]
        if len(runs) == 1:
            filters = filters_per_run[0]
        else:
            filters = {f"{r['tool']}#{i}": f for i, (r, f) in enumerate(zip(runs, filters_per_run), 1) if f}
        result = AssistantAnswer(
            status=state["status"] or "no_data",
            answer=state["answer"],
            evidence=evidence,
            filters=filters,
            sources=_unique(r["result"].get("source") for r in runs),
            measures=_unique(r["arguments"].get("metric") for r in runs),
            limitations=_unique(state.get("limitations", [])),
            trace=state.get("trace", []),
            model=getattr(llm, "deployment_name", None) or getattr(llm, "model_name", None),
            tool_rounds=state.get("rounds", 0),
        )
        return {"result": result}

    # ---- edges -----------------------------------------------------------------------------------------------
    def after_guard(state: AssistantState) -> str:
        return "finish" if state.get("status") == "refused" else "agent"

    def after_agent(state: AssistantState) -> str:
        return "tools" if state["messages"][-1].tool_calls else "compose"

    def after_tools(state: AssistantState) -> str:
        return "compose" if state["rounds"] >= MAX_ROUNDS else "agent"

    graph = StateGraph(AssistantState)
    graph.add_node("guard", guard)
    graph.add_node("agent", agent)
    graph.add_node("tools", tools_node)
    graph.add_node("compose", compose)
    graph.add_node("ground", ground)
    graph.add_node("finish", finish)
    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", after_guard, ["agent", "finish"])
    graph.add_conditional_edges("agent", after_agent, ["tools", "compose"])
    graph.add_conditional_edges("tools", after_tools, ["agent", "compose"])
    graph.add_edge("compose", "ground")
    graph.add_edge("ground", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def run(question: str, repo, llm) -> dict[str, Any]:
    """Run the graph once and return its final state (answer() in __init__ adds error mapping and logging)."""
    return build_graph(repo, llm).invoke({"question": question})
