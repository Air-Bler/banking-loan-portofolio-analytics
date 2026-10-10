"""Grounding: every number in the model's answer must come from a tool result or from the question.

Pure code, no model. The answer may round a source value to its own decimals and may show a ratio as a percentage
(0.5921 covers 0.5921, 0.59, 59.2%, 59,2% and 59 %); it may not invent, convert units (1.2m) or compute new figures.
Years, dates and identifiers (BR003, LA000225, APP-03) are not claims about the data and are skipped.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

_MONTHS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
    r"nov(?:ember)?|dec(?:ember)?|"
    # Greek month stems: the accent moves between the nominative (Δεκέμβριος) and the genitive (Δεκεμβρίου)
    r"ιανου[αά]ρ\w*|φεβρου[αά]ρ\w*|μ[αά]ρτ\w*|απρ[ιί]λ\w*|μ[αά][ιϊΐ]\w*|ιο[υύ]ν\w*|ιο[υύ]λ\w*|α[υύ]γουστ\w*|"
    r"σεπτ[εέ]μβρ\w*|οκτ[ωώ]βρ\w*|νο[εέ]μβρ\w*|δεκ[εέ]μβρ\w*"
)
# things that look like numbers but are not claims about the data; replaced by a space before extraction
_SKIP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"  # 2025-12-31
    r"|\b\d{4}-\d{2}\b"  # 2025-12
    r"|\b\d{1,2}[/.]\d{1,2}[/.]\d{4}\b"  # 31/12/2025
    rf"|\b\d{{1,2}}(?:st|nd|rd|th|η|ης)?\s+(?:{_MONTHS})\b"  # 31 December, 31η Δεκεμβρίου
    rf"|\b(?:{_MONTHS})\.?\s+\d{{1,2}}\b"  # December 31
    r"|\b[A-Za-z]{2,}-\d+\b"  # APP-03, CUS-02 (BR003 and LA000225 are skipped by the number pattern itself)
    r"|^\s*\d+[.)]\s",  # "1. " list markers
    re.IGNORECASE | re.MULTILINE,
)
_NUMBER = re.compile(
    r"(?<![\w.,])"
    r"(?P<num>\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?(?!\d)|\d+(?:[.,]\d+)?)"
    r"(?=(?:[kKmM]|bn|mn|million|thousand|billion)\b|[^A-Za-z]|$)"  # 3f9a1c0b is a key and 3rd a rank; 1.2m is a claim
    r"(?P<pct>\s?(?:%|percent\b|per cent\b|pct\b|τοις εκατό|τοις εκατο))?",
    re.IGNORECASE,
)


def _candidates(token: str) -> list[tuple[Decimal, int]]:
    """Every way to read one written number as (value, decimals shown). '1,234' is ambiguous, so it has two."""
    has_dot, has_comma = "." in token, "," in token
    try:
        if has_dot and has_comma:
            decimal_sep = "." if token.rfind(".") > token.rfind(",") else ","
            thousands_sep = "," if decimal_sep == "." else "."
            whole, _, frac = token.replace(thousands_sep, "").partition(decimal_sep)
            return [(Decimal(f"{whole}.{frac}"), len(frac))]
        if not has_dot and not has_comma:
            return [(Decimal(token), 0)]
        sep = "." if has_dot else ","
        parts = token.split(sep)
        if len(parts) > 2:  # 1,234,567
            return [(Decimal("".join(parts)), 0)]
        before, after = parts
        decimal = (Decimal(f"{before}.{after}"), len(after))
        if len(after) == 3 and 1 <= len(before) <= 3 and not before.startswith("0"):
            return [(Decimal(before + after), 0), decimal]  # 1,234 is 1234 or 1.234
        return [decimal]
    except InvalidOperation:
        return []


def _numbers(text: str) -> list[tuple[str, list[tuple[Decimal, int]], bool]]:
    """(text as written, readings, shown as a percentage) for every number-like token in text."""
    cleaned = _SKIP.sub(" ", text)
    return [(m.group(0).strip(), _candidates(m["num"]), bool(m["pct"])) for m in _NUMBER.finditer(cleaned)]


def _is_year(token: str, readings: list[tuple[Decimal, int]], percent: bool) -> bool:
    return not percent and token.isdigit() and len(token) == 4 and 1900 <= int(token) <= 2100


def _source_values(node: Any, out: set[Decimal]) -> None:
    """Every number inside a tool result or its arguments, including numbers written in labels and definitions."""
    if isinstance(node, bool) or node is None:
        return
    if isinstance(node, (int, float, Decimal)):
        try:
            value = Decimal(str(node))
        except InvalidOperation:
            return
        if value.is_finite():
            out.add(value)
    elif isinstance(node, dict):
        for value in node.values():
            _source_values(value, out)
    elif isinstance(node, (list, tuple)):
        out.add(Decimal(len(node)))  # "3 exceptions" is a count of what was returned
        for value in node:
            _source_values(value, out)
    else:
        for _, readings, _ in _numbers(str(node)):
            out.update(value for value, _ in readings)


def _rounds_to(source: Decimal, value: Decimal, decimals: int) -> bool:
    quantum = Decimal(1).scaleb(-decimals)
    return any(source.quantize(quantum, rounding=mode) == value for mode in (ROUND_HALF_UP, ROUND_HALF_EVEN))


def _grounded(readings: list[tuple[Decimal, int]], percent: bool, sources: set[Decimal]) -> bool:
    for value, decimals in readings:
        for source in sources:
            options = (source, source * 100) if percent else (source,)  # 0.5921 may be written as 59.2%
            if any(_rounds_to(option, value, decimals) for option in options):
                return True
    return False


def ungrounded_numbers(text: str, question: str, runs: list[dict]) -> list[str]:
    """The numbers of text that appear neither in the tool runs nor in the question (as written, e.g. '71%')."""
    sources: set[Decimal] = set()
    for run in runs:
        _source_values(run.get("arguments"), sources)
        _source_values(run.get("result"), sources)
    for _, readings, _ in _numbers(question):
        sources.update(value for value, _ in readings)

    bad = []
    for token, readings, percent in _numbers(text):
        if not readings or _is_year(token, readings, percent):
            continue
        if not _grounded(readings, percent, sources) and token not in bad:
            bad.append(token)
    return bad


# ---- the neutral answer used when the wording failed the check ---------------------------------------------------------------
def _number(value: Any, unit: str | None = None) -> str:
    if value is None:
        return "n/a"
    value = float(value)
    if unit == "ratio":
        return f"{value * 100:.2f}%"
    if unit == "EUR":
        return f"EUR {value:,.2f}"
    if unit == "days":
        return f"{value:,.2f} days"
    return f"{value:,.0f}" if value == int(value) else f"{value:,.2f}"


def _kpi_lines(result: dict) -> list[str]:
    metric = result.get("metric") or {}
    unit = metric.get("unit")
    lines = [f"{metric.get('label', 'KPI')}: {metric.get('definition', '')}".rstrip(": ")]
    if result.get("filters"):
        lines.append("Filters: " + ", ".join(f"{k}={v}" for k, v in result["filters"].items()))
    for row in result.get("rows", []):
        label = f"{result['group_by']} {row['group']}" if result.get("group_by") else "Whole portfolio"
        if result.get("group_by") is None and row.get("group"):
            label = str(row["group"])  # dti_band_share rows carry their band as the group
        detail = ""
        if row.get("denominator") is not None and unit == "ratio":
            detail = f" ({_number(row.get('numerator'))} of {_number(row['denominator'])})"
        lines.append(f"- {label}: {_number(row.get('value'), unit)}{detail}")
    return lines


def _exception_lines(result: dict) -> list[str]:
    items = result.get("items", [])
    lines = [f"Data-quality exceptions: {_number(result.get('total'))} in total, showing {_number(len(items))}."]
    for item in items[:10]:
        lines.append(f"- {item.get('rule_id')} ({item.get('action')}): {item.get('description')}, branch {item.get('branch_code')}")
    return lines


def _metadata_lines(result: dict) -> list[str]:
    lines = ["Available metrics:"]
    lines += [f"- {m['name']} ({m['unit']}): {m['definition']}" for m in result.get("metrics", [])]
    return lines


def _exposure_lines(result: dict) -> list[str]:
    return [
        f"Household exposure for application {result.get('application_id')}: {_number(result.get('members'))} borrowers, "
        f"{_number(len(result.get('applications', [])))} applications, total outstanding {_number(result.get('total_outstanding'), 'EUR')}, "
        f"delinquent loans: {_number(result.get('delinquent_loans'))}."
    ]


_SUMMARISERS = {
    "get_portfolio_kpi": _kpi_lines,
    "get_dq_exceptions": _exception_lines,
    "get_metadata": _metadata_lines,
    "get_connected_exposure": _exposure_lines,
}


def summarise(runs: list[dict]) -> str:
    """A neutral answer written by code from the raw results (used when the model's wording is not grounded)."""
    if not runs:
        return "No data was retrieved."
    blocks = []
    for run in runs:
        result = run.get("result") or {}
        lines = _SUMMARISERS.get(run.get("tool"), lambda r: [str(r)[:300]])(result)
        footer = f"Source: {result.get('source', 'unknown')}; data as of {result.get('as_of_date', 'unknown')}."
        blocks.append("\n".join([*lines, footer]))
    return "\n\n".join(blocks)
