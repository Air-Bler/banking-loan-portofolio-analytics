"""Ask the real model each question of eval/questions.yaml and print a pass/fail table.

    uv run python -m eval.run_eval              # all questions
    uv run python -m eval.run_eval --demo       # only the questions marked demo: true
    uv run python -m eval.run_eval --markdown   # also print the table as markdown (for docs/07_langchain.md)

It needs the real Gold repository and Azure OpenAI. Settings come from the environment; the repo-root .env is only a
fallback (variables that are already set win). The first lines of the output name the model and endpoint so a wrong
.env is easy to spot. Wake the SQL warehouse first: a stopped one makes the first tool call time out and shows as no_data.

A question passes when the status is one of the expected ones, the expected tool ran, an `answered` question has
evidence, and the grounding check did not have to replace the model's wording.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from api.assistant.schemas import AssistantAnswer

QUESTIONS = Path(__file__).with_name("questions.yaml")
GROUNDING_NOTE = "numbers not found in the data"  # in the limitation api/assistant/graph.py adds when it replaces an answer


@dataclass
class Row:
    item: dict
    result: AssistantAnswer | None = None
    problems: list[str] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return not self.problems


def load_questions(path: Path = QUESTIONS, demo_only: bool = False) -> list[dict]:
    items = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [item for item in items if item.get("demo")] if demo_only else items


def expected_statuses(item: dict) -> list[str]:
    status = item["status"]
    return list(status) if isinstance(status, list) else [status]


def judge(item: dict, result: AssistantAnswer) -> list[str]:
    """Why the answer does not meet the question's expectations (empty list = pass)."""
    problems = []
    expected = expected_statuses(item)
    if result.status not in expected:
        problems.append(f"status {result.status}, expected {' or '.join(expected)}")
    tools_run = [step["tool"] for step in result.trace]
    if item.get("tool") and item["tool"] not in tools_run:
        problems.append(f"{item['tool']} did not run (ran: {', '.join(tools_run) or 'nothing'})")
    if expected == ["answered"] and not result.evidence:
        problems.append("answered without evidence")
    if any(GROUNDING_NOTE in limitation for limitation in result.limitations):
        problems.append("grounding replaced the model's wording")
    return problems


def run_question(item: dict, repo, llm) -> Row:
    """Ask one question. An error from Databricks or Azure is a failed row, not a crash."""
    from api.assistant import answer

    row = Row(item)
    started = time.perf_counter()
    try:
        row.result = answer(item["question"], repo, llm)
        row.problems = judge(item, row.result)
    except Exception as exc:  # noqa: BLE001 - report it and go on with the next question
        row.problems = [f"error: {type(exc).__name__}"]
    row.seconds = time.perf_counter() - started
    return row


def _tools(row: Row) -> str:
    return ", ".join(dict.fromkeys(step["tool"] for step in row.result.trace)) if row.result else ""


def format_table(rows: list[Row]) -> str:
    lines = []
    for number, row in enumerate(rows, 1):
        got = row.result.status if row.result else "error"
        lines.append(f"{'PASS' if row.passed else 'FAIL'}  {number:>2}  {got:<10} {row.seconds:>5.1f}s  "
                     f"{_tools(row) or '-':<24} {row.item['question'][:58]}")
    return "\n".join(lines)


def format_markdown(rows: list[Row]) -> str:
    lines = ["| # | Question | Expected | Got | Tools | Result |", "|---|---|---|---|---|---|"]
    for number, row in enumerate(rows, 1):
        got = row.result.status if row.result else "error"
        question = row.item["question"].replace("|", "\\|")
        lines.append(f"| {number} | {question} | {' or '.join(expected_statuses(row.item))} | {got} | {_tools(row) or '-'} | "
                     f"{'pass' if row.passed else 'FAIL: ' + '; '.join(row.problems)} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="only the questions marked demo: true")
    parser.add_argument("--markdown", action="store_true", help="also print the results as a markdown table")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

    from api.assistant.llm import get_llm
    from api.errors import AssistantUnavailable
    from api.queries import GoldRepository
    from api.settings import Settings

    settings = Settings()
    try:
        llm = get_llm(settings)
    except AssistantUnavailable as exc:
        print(f"Azure OpenAI is not configured: {exc}", file=sys.stderr)
        return 2
    host = urlparse(settings.azure_openai_endpoint).netloc
    print(f"Model: {settings.azure_openai_deployment} @ {host} (api {settings.azure_openai_api_version})")
    print(f"Gold:  {settings.databricks_catalog}.{settings.databricks_schema}")

    repo = GoldRepository(settings)
    try:
        info = repo.refresh_info()
    except Exception as exc:  # noqa: BLE001 - the usual cause is a stopped warehouse or a stale token
        print(f"Cannot read Gold ({type(exc).__name__}). Is the SQL warehouse running and the token valid?", file=sys.stderr)
        return 2
    print(f"Data as of {info['as_of_date']}\n")

    items = load_questions(demo_only=args.demo)
    rows = [run_question(item, repo, llm) for item in items]
    print(format_table(rows))
    failed = [row for row in rows if not row.passed]
    for row in failed:
        print(f"\nFAIL: {row.item['question']}\n  " + "\n  ".join(row.problems))
        if row.result:
            print(f"  answer: {row.result.answer[:300]}")
    print(f"\n{len(rows) - len(failed)}/{len(rows)} passed")
    if args.markdown:
        print("\n" + format_markdown(rows))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
