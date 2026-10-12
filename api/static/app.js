// Loan Portfolio Analytics: a thin client over the API. Every number on screen comes from an API
// response; this file only arranges and formats it. Data is inserted with textContent, never as HTML.
"use strict";

const BRANCHES = [...Array.from({ length: 12 }, (_, i) => `BR${String(i + 1).padStart(3, "0")}`), "UNKNOWN"];
const YEARS = Array.from({ length: 10 }, (_, i) => 2016 + i);
const RULES = [
  ...range("CUS", 1, 6), ...range("APP", 1, 12), ...range("REP", 1, 8), ...range("TRX", 0, 9), "MAC-01",
];
const PRODUCTS = {
  "PL-STD": "Personal loan", "PL-GRN": "Green home loan", "AUT-NEW": "New car loan",
  "MTG-FIX": "Fixed-rate mortgage", "SME-WCL": "SME working capital", UNKNOWN: "Unknown",
};
const KPI_NOTES = {
  applications: "After data-quality checks",
  requested_amount: "Sum of requested principal",
  approval_rate: "Approved ÷ (approved + rejected)",
  avg_decision_days: "Application to decision",
  high_dti_share: "Debt-to-income 35% or more",
  delinquency_rate_30: "Active loans 30+ days late",
  outstanding_balance: "Outstanding principal",
  manual_review_rate: "Sent to manual review",
};
const PAGE_SIZE = 20;

function range(prefix, from, to) {
  return Array.from({ length: to - from + 1 }, (_, i) => `${prefix}-${String(from + i).padStart(2, "0")}`);
}

// ======================================================================================
// Credential, chosen by the environment /health reports:
//   prod        -> "Sign in with Microsoft" (auth.js); every call sends Authorization: Bearer <token>
//   dev, local  -> an API key entered once per tab; every call sends X-API-Key
// Both live in sessionStorage, so they are forgotten when the tab closes.
// ======================================================================================

const store = {
  get(k) { try { return sessionStorage.getItem(k) || ""; } catch { return ""; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch { /* storage blocked: memory only */ } },
};
let useSignIn = false; // set from /health at start-up
const apiKey = { value: store.get("apiKey") };
let signInMessage = ""; // shown on the sign-in card after a failed or expired sign-in

let signInRejected = false; // the API refused our token: show the sign-in card instead of retrying

const connected = () => (useSignIn ? Boolean(auth.account()) && !signInRejected : Boolean(apiKey.value));

async function authHeaders() {
  if (!useSignIn) return apiKey.value ? { "X-API-Key": apiKey.value } : {};
  const token = await auth.getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function onUnauthorized(message) {
  if (!useSignIn) { askForKey(message); return; }
  // Re-render once to show the sign-in card. Re-rendering on every 401 loops: the page calls the
  // API again, gets another 401, re-renders, and so on.
  if (signInRejected) return;
  signInRejected = true;
  signInMessage = message;
  updateAuthUi();
  route();
}

// ======================================================================================
// API client
// ======================================================================================

class ApiError extends Error {
  constructor(status, error = {}) {
    super(error.message || `HTTP ${status}`);
    this.status = status;
    this.code = error.code || "error";
    this.correlationId = error.correlation_id;
    this.details = error.details || [];
  }
}

async function api(path, body) {
  let headers;
  try {
    headers = await authHeaders();
  } catch (err) { // the token could not be renewed, even with a popup
    onUnauthorized(auth.describeError(err));
    throw new ApiError(401, { code: "unauthorized", message: auth.describeError(err) });
  }
  const init = { headers };
  if (body !== undefined) {
    init.method = "POST";
    init.headers = { ...init.headers, "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError(0, { code: "network_error", message: "The API could not be reached." });
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new ApiError(response.status, data.error || { correlation_id: response.headers.get("X-Correlation-ID") });
    if (err.code === "unauthorized") {
      onUnauthorized(useSignIn ? "Your session has ended. Sign in again." : "The API rejected the credential. Enter a valid one.");
    }
    throw err;
  }
  return data;
}

const query = (metric, extra = {}) => api("/analytics/query", { metric, limit: 1000, ...extra });

// Metric catalogue (labels, units, definitions), loaded once.
let metrics = null;
async function loadMetrics() {
  if (!metrics) {
    const res = await api("/metadata/metrics");
    metrics = Object.fromEntries(res.metrics.map((m) => [m.name, m]));
  }
  return metrics;
}
const KPIS = () => Object.keys(metrics).filter((n) => n !== "dti_band_share");
const unitOf = (n) => metrics?.[n]?.unit;
const labelOf = (n) => metrics?.[n]?.label || n;

// Whole-portfolio KPI values, cached for the branch comparison.
let portfolio = null;
async function portfolioKpis() {
  if (!portfolio) {
    await loadMetrics();
    const entries = await Promise.all(KPIS().map(async (n) => [n, (await query(n)).rows[0]]));
    portfolio = Object.fromEntries(entries);
  }
  return portfolio;
}

// ======================================================================================
// DOM and formatting helpers
// ======================================================================================

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  append(node, children);
  return node;
}

function append(node, children) {
  for (const child of [children].flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function fill(node, ...children) {
  node.replaceChildren();
  return append(node, children);
}

const nf = new Intl.NumberFormat("en-GB");
const eur0 = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });
const eurC = new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR", notation: "compact", maximumFractionDigits: 1 });
const dateLong = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function fmt(value, unit, { compact = true } = {}) {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (typeof value !== "number") return String(value);
  switch (unit) {
    case "ratio": return `${(value * 100).toFixed(1)}%`;
    case "EUR": return compact ? eurC.format(value) : eur0.format(value);
    case "days": return `${value.toFixed(1)} days`;
    case "count": return nf.format(Math.round(value));
    default: return nf.format(Math.round(value * 100) / 100);
  }
}
const fmtDate = (iso) => (iso ? dateLong.format(new Date(`${iso}T00:00:00Z`)) : "–");
const fmtDateTime = (iso) => (iso ? iso.replace("T", " ").slice(0, 16) : "–");
const short = (id) => (id && id.length > 14 ? `${id.slice(0, 6)}…${id.slice(-4)}` : id);
const nodeId = (id) => (id || "").replace(/^customer:/, "");

function errorBox(err) {
  if (err.code === "assistant_unavailable") {
    return el("div", { class: "alert notice" },
      el("strong", {}, "The assistant is not available on this environment. "),
      "Azure OpenAI is not configured or is down; the rest of the dashboard works without it. ",
      el("code", {}, `correlation id ${err.correlationId || "–"}`));
  }
  const hint = {
    unauthorized: useSignIn ? "Sign in again with the button in the top bar." : "Use the key button in the top bar to enter a valid API key.",
    data_unavailable: "The data warehouse is unavailable or still waking up. Try again in a minute.",
    validation_error: err.details.map((d) => `${d.field}: ${d.message}`).join("; "),
  }[err.code] || "";
  return el("div", { class: "alert error" }, el("strong", {}, err.message), hint ? ` ${hint} ` : " ",
    el("code", {}, `${err.code}${err.correlationId ? ` · correlation id ${err.correlationId}` : ""}`));
}

function table(columns, rows, attrs = {}) {
  // columns: [{label, num?, cls?, render(row) | key}]
  return el("div", { class: `table-wrap ${attrs.framed ? "framed" : ""}` }, el("table", { class: attrs.cls },
    el("thead", {}, el("tr", {}, columns.map((c) => el("th", { class: c.num ? "num" : null }, c.label)))),
    el("tbody", {}, rows.map((r) => el("tr", { class: attrs.rowClass?.(r) }, columns.map((c) =>
      el("td", { class: [c.num ? "num" : "", c.cls || ""].join(" ").trim() || null }, c.render ? c.render(r) : r[c.key] ?? "–")))))));
}

function tile(label, value, sub, opts = {}) {
  return el("div", { class: `tile ${opts.compact ? "compact" : ""}`, title: opts.title },
    el("div", { class: "label" }, label),
    el("div", { class: `value ${opts.tone || ""}` }, value),
    sub ? el("div", { class: "sub" }, sub) : null);
}

function hbars(rows, { color = "var(--primary)", colors, format = (v) => nf.format(v), max } = {}) {
  const top = max ?? (Math.max(...rows.map((r) => r.value ?? 0), 0) || 1);
  return el("div", { class: "hbars" }, rows.map((r, i) => [
    el("div", { class: "lab", title: r.label }, r.label),
    el("div", { class: "track" }, el("div", {
      class: "fill", style: `width:${Math.max(0, Math.min(100, ((r.value ?? 0) / top) * 100))}%;background:${colors?.[i] || color}`,
    })),
    el("div", { class: "num" }, r.value === null || r.value === undefined ? "–" : format(r.value)),
  ]));
}

const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function vbars(rows, format = (v) => nf.format(v)) {
  const data = rows.filter((r) => typeof r.value === "number");
  if (!data.length) return el("p", { class: "empty" }, "No data for this selection.");
  const W = 600, H = 250, bottom = 26, top = 22, max = Math.max(...data.map((r) => r.value)) || 1;
  const slot = W / data.length, barW = Math.min(44, slot * 0.72);
  const chart = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img" });
  chart.append(svg("line", { x1: 0, x2: W, y1: H - bottom, y2: H - bottom, stroke: "#c9d0d7" }));
  const every = Math.ceil(data.length / 12);
  data.forEach((r, i) => {
    const h = Math.max(1, (r.value / max) * (H - bottom - top));
    const x = i * slot + (slot - barW) / 2, y = H - bottom - h;
    const bar = svg("rect", { x, y, width: barW, height: h, fill: "#1f4e89", rx: 2 });
    bar.append(svg("title", {}, `${r.label}: ${format(r.value)}`));
    chart.append(bar);
    if (data.length <= 16) chart.append(svg("text", { x: x + barW / 2, y: y - 7, "text-anchor": "middle" }, format(r.value)));
    if (i % every === 0) chart.append(svg("text", { class: "axis", x: x + barW / 2, y: H - 7, "text-anchor": "middle" }, r.label));
  });
  return el("div", { class: "vbars" }, chart);
}

function loading(text = "Loading…") { return el("p", { class: "empty" }, text); }

function options(values, selected, label = (v) => v) {
  return values.map((v) => el("option", { value: v, selected: String(v) === String(selected) }, label(v)));
}

// ======================================================================================
// Pages
// ======================================================================================

const view = $("view");
let renderToken = 0; // a newer navigation makes older async renders stop writing to the page

function head(title, sub, right) {
  return el("div", { class: "page-head" },
    el("div", {}, el("div", { class: "title" }, el("h1", {}, title)), sub ? el("p", {}, sub) : null),
    right);
}

// ---------- Overview ----------

async function pageOverview(params, token) {
  await loadMetrics();
  const period = params.get("year") || "all";
  const branch = params.get("branch") || "";
  const filters = {};
  if (period !== "all") Object.assign(filters, { date_from: `${period}-01-01`, date_to: `${period}-12-31` });
  if (branch) filters.branch_code = branch;

  const yearSel = el("select", { id: "f-year" }, el("option", { value: "all" }, "2016 – 2025"), options(YEARS, period));
  const branchSel = el("select", { id: "f-branch" }, el("option", { value: "" }, "All branches"), options(BRANCHES, branch));
  yearSel.value = period;
  const apply = () => go("overview", { year: yearSel.value === "all" ? null : yearSel.value, branch: branchSel.value || null });

  const tiles = el("div", { class: "grid cols-4" }, KPIS().map((n) => el("div", { class: "tile loading", id: `t-${n}` },
    el("div", { class: "label" }, labelOf(n)), el("div", { class: "value" }, "—"), el("div", { class: "sub" }, KPI_NOTES[n] || ""))));
  const yearCard = el("div", { class: "card" }, el("div", { class: "card-head" },
    el("h2", {}, period === "all" ? "Applications per year" : `Applications per month, ${period}`),
    el("span", { class: "src" }, "kpi_portfolio_monthly")), loading());
  const dtiCard = el("div", { class: "card" }, el("div", { class: "card-head" },
    el("h2", {}, "Debt-to-income bands"), el("span", { class: "src" }, "kpi_portfolio_summary")), loading());
  const branchCard = el("div", { class: "card section" }, el("div", { class: "card-head" },
    el("h2", {}, "By branch"), el("a", { href: "#/branches" }, "Open branch drill-through")), loading());

  fill(view,
    head("Portfolio overview", "The 8 governed KPIs from the Gold layer, with the same definitions as the Power BI report.",
      el("form", { class: "filters", onsubmit: (e) => { e.preventDefault(); apply(); } },
        el("label", { class: "field" }, "Period", yearSel),
        el("label", { class: "field" }, "Branch", branchSel),
        el("button", { class: "btn", type: "submit" }, "Apply"))),
    tiles,
    el("div", { class: "grid cols-2 section" }, yearCard, dtiCard),
    branchCard);

  const f = Object.keys(filters).length ? { filters } : {};

  // KPI tiles
  KPIS().forEach(async (n) => {
    const node = $(`t-${n}`);
    try {
      const res = await query(n, f);
      if (token !== renderToken) return;
      node.classList.remove("loading");
      node.querySelector(".value").textContent = fmt(res.rows[0]?.value, unitOf(n));
      node.title = metrics[n].definition;
    } catch (err) {
      if (token !== renderToken) return;
      node.querySelector(".value").textContent = "–";
      node.title = err.message;
    }
  });

  // Applications per year (or per month inside one year)
  query("applications", { ...f, group_by: period === "all" ? "year" : "month" }).then((res) => {
    if (token !== renderToken) return;
    const rows = res.rows.map((r) => ({ label: period === "all" ? r.group : r.group.slice(4), value: r.value }))
      .sort((a, b) => a.label.localeCompare(b.label));
    yearCard.lastChild.replaceWith(vbars(rows));
  }).catch((err) => token === renderToken && yearCard.lastChild.replaceWith(errorBox(err)));

  // DTI bands: Gold has them for the whole portfolio only
  query("dti_band_share").then((res) => {
    if (token !== renderToken) return;
    const label = { below_20: "Under 20%", "20_35": "20–35%", "35_50": "35–50%", above_50: "Over 50%" };
    dtiCard.lastChild.replaceWith(el("div", {},
      hbars(res.rows.map((r) => ({ label: label[r.group] || r.group, value: r.value })), {
        colors: ["#1f4e89", "#4f7cb0", "#e4a05a", "#8a3c06"], format: (v) => fmt(v, "ratio"), max: 1,
      }),
      el("p", { class: "note" }, "Share of applications in each debt-to-income band. Gold keeps this KPI for the whole portfolio only, so the period and branch filters do not apply.")));
  }).catch((err) => token === renderToken && dtiCard.lastChild.replaceWith(errorBox(err)));

  // By branch: one grouped query per column, joined on the branch code
  const cols = ["applications", "approval_rate", "avg_decision_days", "delinquency_rate_30", "outstanding_balance"];
  Promise.all(cols.map((n) => query(n, { ...f, group_by: "branch" }))).then((results) => {
    if (token !== renderToken) return;
    const byBranch = {};
    results.forEach((res, i) => res.rows.forEach((r) => { (byBranch[r.group] ??= { code: r.group })[cols[i]] = r.value; }));
    const rows = Object.values(byBranch).sort((a, b) => (b.applications ?? 0) - (a.applications ?? 0));
    branchCard.lastChild.replaceWith(el("div", {},
      table([
        { label: "Branch", render: (r) => el("a", { class: "row-link", href: `#/branches/${r.code}` }, r.code) },
        { label: "Applications", num: true, render: (r) => fmt(r.applications, "count") },
        { label: "Approval rate", num: true, render: (r) => fmt(r.approval_rate, "ratio") },
        { label: "Avg decision (days)", num: true, render: (r) => (r.avg_decision_days ?? null) === null ? "–" : r.avg_decision_days.toFixed(1) },
        { label: "Delinquency 30+", num: true, render: (r) => fmt(r.delinquency_rate_30, "ratio") },
        { label: "Outstanding", num: true, render: (r) => fmt(r.outstanding_balance, "EUR") },
      ], rows),
      el("div", { class: "table-foot" }, el("span", {}, `${rows.length} branches · from POST `, el("code", {}, "/analytics/query")))));
  }).catch((err) => token === renderToken && branchCard.lastChild.replaceWith(errorBox(err)));
}

// ---------- Assistant ----------

const conversation = []; // survives navigation between pages

const SUGGESTIONS = [
  "What was the approval rate by branch in 2025?",
  "Which product has the highest outstanding balance?",
  "Show the 30-day delinquency rate by month for 2025.",
  "What is the connected exposure for application LA000225?",
];
const TOOLS = [
  ["get_portfolio_kpi", "One KPI for the whole portfolio or by branch, product, month or year, optionally for a date range"],
  ["get_dq_exceptions", "Records flagged or rejected by the data-quality rules"],
  ["get_metadata", "The available KPIs, their definitions and how recent the data is"],
  ["get_connected_exposure", "The household around one application and its total outstanding balance"],
];

function pageAssistant() {
  const chat = el("div", { class: "chat" });
  const input = el("input", { id: "ask", maxlength: 1000, placeholder: "e.g. Which branches have the highest delinquency?", autocomplete: "off" });
  const send = el("button", { class: "btn", type: "submit" }, "Ask");

  const render = () => fill(chat, conversation.map(renderTurn), el("form", { class: "card composer", onsubmit: submit },
    el("label", { for: "ask" }, "Ask about the portfolio"),
    el("div", { class: "row" }, input, send),
    el("div", { class: "hint" }, "Sends POST ", el("code", {}, "/assistant/query"), ". Questions about actions or raw SQL are refused before the model is called.")));

  async function ask(question) {
    const turn = { question, pending: true, started: performance.now() };
    conversation.push(turn);
    render();
    send.disabled = true;
    try {
      turn.result = await api("/assistant/query", { question });
    } catch (err) {
      turn.error = err;
    }
    turn.pending = false;
    turn.seconds = (performance.now() - turn.started) / 1000;
    send.disabled = false;
    if (location.hash.startsWith("#/assistant")) { render(); input.focus(); }
  }

  function submit(e) {
    e.preventDefault();
    const q = input.value.trim();
    if (!q || send.disabled) return;
    input.value = "";
    ask(q);
  }

  fill(view,
    head("Portfolio assistant", "Ask a question in plain language. Every number in an answer is copied from a tool result over the Gold layer, and the evidence is shown under it."),
    el("div", { class: "assistant" },
      el("aside", { class: "side" },
        el("div", { class: "card" }, el("h2", {}, "Try asking"),
          SUGGESTIONS.map((s) => el("button", { class: "suggest", type: "button", onclick: () => ask(s) }, s))),
        el("div", { class: "card" }, el("h2", {}, "Tools it can use"),
          TOOLS.map(([name, text]) => el("div", { class: "tool" }, el("div", { class: "mono" }, name), el("p", {}, text))),
          el("hr"), el("h3", {}, "It will not"),
          el("p", { class: "muted small" }, "Approve or change loans, run SQL, show personal data, or answer from memory without a tool result."))),
      chat));
  render();
}

function renderTurn(turn) {
  const bubble = el("div", { class: "bubble" }, turn.question);
  if (turn.pending) return [bubble, el("div", { class: "card answer-card" }, el("p", { class: "muted" }, "Thinking…"))];
  const secs = `${turn.seconds.toFixed(1)} s`;
  if (turn.error) {
    return [bubble, el("div", { class: "card answer-card" },
      el("div", { class: "meta" }, el("span", { class: "badge unavailable" }, "Unavailable"), secs),
      el("div", { class: "section" }, errorBox(turn.error)))];
  }
  const r = turn.result; // the AssistantAnswer of docs/contracts.md section 6, plus correlation_id
  const calls = `${r.evidence.length} tool call${r.evidence.length === 1 ? "" : "s"}`;
  const asOf = r.evidence[0]?.as_of_date;
  const status = {
    answered: ["answered", "Answered", [secs, calls, asOf ? `data as of ${fmtDate(asOf)}` : null].filter(Boolean).join(" · ")],
    refused: ["refused", "Refused", "Outside what the assistant can do"],
    no_data: ["nodata", "No data", secs],
    incomplete: ["incomplete", "Incomplete", `${secs} · stopped before a full answer`],
  }[r.status] || ["nodata", "No data", secs];
  // With several tool calls the filters come per call ({"get_portfolio_kpi#1": {...}}): show them as plain tags too.
  const filterPairs = Object.entries(r.filters || {}).flatMap(([k, v]) => (v && typeof v === "object" ? Object.entries(v) : [[k, v]]));
  const filterTags = [...new Set(filterPairs.map(([k, v]) => `${k}: ${v}`))].map((t) => el("span", { class: "tag" }, t));
  const rounds = `${r.tool_rounds} tool round${r.tool_rounds === 1 ? "" : "s"}`;

  return [bubble, el("div", { class: "card answer-card" },
    el("div", { class: "meta" }, el("span", { class: `badge ${status[0]}` }, status[1]), status[2]),
    el("p", { class: "answer-text" }, r.answer),
    r.evidence.map(evidenceBlock),
    el("div", { class: "answer-facts" },
      el("div", {}, el("h3", {}, "Filters applied"), filterTags.length ? filterTags : el("span", { class: "muted" }, "None")),
      el("div", {}, el("h3", {}, "Source"), r.sources.length ? r.sources.map((s) => el("div", { class: "mono" }, s)) : el("span", { class: "muted" }, "No tool was run")),
      el("div", {}, el("h3", {}, "Limitations"), r.limitations.length ? el("ul", {}, r.limitations.map((l) => el("li", {}, l))) : el("span", { class: "muted" }, "None"))),
    el("div", { class: "trace" }, [`correlation id ${r.correlation_id || "–"}`, r.model, rounds].filter(Boolean).join(" · ")))];
}

// One box per tool call that returned data: what was read, from which Gold table, and how recent it is.
function evidenceBlock(e) {
  const [title, body] = evidenceContent(e.tool, e.result || {});
  return el("div", { class: "evidence" },
    el("div", { class: "evidence-head" }, el("span", {}, `Evidence · ${title}`),
      el("span", { class: "mono muted" }, [e.tool, e.source, e.as_of_date ? `as of ${fmtDate(e.as_of_date)}` : null].filter(Boolean).join(" · "))),
    body);
}

// The tool's raw result as a title and a table, formatted like the rest of the dashboard.
function evidenceContent(tool, res) {
  if (tool === "get_portfolio_kpi") {
    const unit = res.metric?.unit;
    const group = res.group_by ? res.group_by[0].toUpperCase() + res.group_by.slice(1) : "Group";
    return [res.metric?.label || "KPI", table([
      { label: group, render: (row) => row.group ?? res.filters?.branch_code ?? "Whole portfolio" },
      { label: "Value", num: true, render: (row) => fmt(row.value, unit, { compact: false }) },
    ], res.rows || [])];
  }
  if (tool === "get_dq_exceptions") {
    const items = res.items || [];
    const total = res.total ?? items.length;
    const count = total > items.length ? `${nf.format(total)} in total · first ${items.length} shown` : `${nf.format(total)} in total`;
    return [`Data-quality exceptions · ${count}`, table([
      { label: "Rule", cls: "mono", key: "rule_id" },
      { label: "Action", key: "action" },
      { label: "Description", key: "description" },
      { label: "Branch", cls: "mono", key: "branch_code" },
    ], items)];
  }
  if (tool === "get_connected_exposure") {
    const summary = `${res.members} members · ${fmt(res.total_outstanding, "EUR", { compact: false })} outstanding · ${res.delinquent_loans} delinquent`;
    return [`Connected exposure · ${summary}`, table([
      { label: "Application", cls: "mono", key: "application_id" },
      { label: "Customer", cls: "mono", render: (row) => nodeId(row.customer_node) },
      { label: "Status", key: "status_code" },
      { label: "Outstanding", num: true, render: (row) => fmt(row.outstanding_balance, "EUR", { compact: false }) },
      { label: "30+ days late", render: (row) => (row.is_delinquent_30 ? "Yes" : "No") },
    ], res.applications || [])];
  }
  if (tool === "get_metadata") {
    return ["Available KPIs", table([
      { label: "KPI", key: "label" },
      { label: "Unit", key: "unit" },
      { label: "Definition", key: "definition" },
    ], res.metrics || [])];
  }
  // A tool this page doesn't know yet: show its plain values.
  const plain = Object.entries(res).filter(([, v]) => v === null || typeof v !== "object");
  return [tool, table([{ label: "Field", key: "k" }, { label: "Value", key: "v" }], plain.map(([k, v]) => ({ k, v })))];
}

// ---------- Branches ----------

async function pageBranches(params, token, code) {
  code = code || "BR003";
  await loadMetrics();
  const select = el("select", { onchange: (e) => go(`branches/${e.target.value}`) }, options(BRANCHES, code));

  const tiles = el("div", { class: "grid cols-4" }, KPIS().map((n) => tile(labelOf(n), "—", "", { compact: true })));
  const funnel = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Application funnel")), loading());
  const products = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Applications by product")), loading());
  const approval = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Approval rate by product")), loading());
  const delinquency = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Delinquency 30+ by product")), loading());
  const dq = el("div", { class: "card section" }, loading("Counting data-quality exceptions…"));
  const title = el("h1", {}, code);
  const sub = el("p", {}, "");

  fill(view,
    el("div", { class: "crumbs" }, el("a", { href: "#/overview" }, "Overview"), " / Branches / ", code),
    el("div", { class: "page-head" },
      el("div", {}, el("div", { class: "title" }, title, el("span", { class: "chip-code" }, code)), sub),
      el("label", { class: "field" }, "Branch", select)),
    tiles,
    el("div", { class: "grid cols-2 section" }, funnel, products),
    el("div", { class: "grid cols-2 section" }, approval, delinquency),
    dq);

  let summary;
  try {
    summary = await api(`/branches/${encodeURIComponent(code)}/summary`);
  } catch (err) {
    if (token !== renderToken) return;
    fill(view, el("div", { class: "crumbs" }, el("a", { href: "#/overview" }, "Overview"), " / Branches / ", code),
      el("div", { class: "page-head" }, el("h1", {}, code), el("label", { class: "field" }, "Branch", select)), errorBox(err));
    return;
  }
  if (token !== renderToken) return;
  title.textContent = summary.branch_name;
  sub.textContent = `${fmt(summary.kpis.applications, "count")} applications since 2016 · data as of ${fmtDate(summary.as_of_date)}`;

  // KPI tiles with the portfolio for comparison: share of portfolio for totals, the portfolio value for rates
  portfolioKpis().catch(() => ({})).then((pf) => {
    if (token !== renderToken) return;
    fill(tiles, KPIS().map((n) => {
      const v = summary.kpis[n], p = pf?.[n]?.value, unit = unitOf(n);
      let note = "";
      if (typeof p === "number" && typeof v === "number") {
        note = unit === "count" || unit === "EUR" ? `${((v / p) * 100).toFixed(1)}% of portfolio`
          : `Portfolio ${unit === "days" ? p.toFixed(1) : fmt(p, unit)}`;
      }
      return tile(labelOf(n), fmt(v, unit), note, { compact: true, title: metrics[n].definition });
    }));
  });

  // Funnel from the numerators and denominators of the branch's own rates
  const bf = { filters: { branch_code: code } };
  Promise.all([query("approval_rate", bf), query("delinquency_rate_30", bf)]).then(([appr, del]) => {
    if (token !== renderToken) return;
    const a = appr.rows[0] || {}, d = del.rows[0] || {};
    funnel.lastChild.replaceWith(el("div", {}, hbars([
      { label: "Submitted", value: summary.kpis.applications },
      { label: "Decided", value: a.denominator },
      { label: "Approved", value: a.numerator },
      { label: "Active loans", value: d.denominator },
      { label: "Delinquent 30+", value: d.numerator },
    ], { colors: ["#1f4e89", "#1f4e89", "#1f4e89", "#1f4e89", "#b45309"], format: (v) => fmt(v, "count") }),
    el("p", { class: "note" }, "Decided = approved + rejected. Active loans are approved loans not yet paid off.")));
  }).catch((err) => token === renderToken && funnel.lastChild.replaceWith(errorBox(err)));

  const prodRows = (key) => summary.by_product
    .map((p) => ({ label: PRODUCTS[p.product_code] || p.product_code, value: p.kpis[key] }))
    .sort((x, y) => (y.value ?? 0) - (x.value ?? 0));
  products.lastChild.replaceWith(hbars(prodRows("applications"), { color: "#4f7cb0", format: (v) => fmt(v, "count") }));
  approval.lastChild.replaceWith(hbars(prodRows("approval_rate"), { color: "#1f4e89", format: (v) => fmt(v, "ratio"), max: 1 }));
  delinquency.lastChild.replaceWith(hbars(prodRows("delinquency_rate_30"), { color: "#b45309", format: (v) => fmt(v, "ratio") }));

  // Data-quality exceptions at this branch: totals from /exceptions
  Promise.all(["REJECT", "FLAG"].map((action) =>
    api(`/exceptions?${new URLSearchParams({ branch_code: code, action, limit: 1 })}`))).then(([rej, flag]) => {
    if (token !== renderToken) return;
    fill(dq, el("div", { class: "banner" },
      el("span", { style: "color:var(--orange);font-size:1.2rem" }, "⚠"),
      el("div", { class: "grow" }, el("strong", {}, `${nf.format(rej.total + flag.total)} data-quality exceptions`),
        ` at this branch: ${nf.format(rej.total)} rejected, ${nf.format(flag.total)} flagged`),
      el("a", { href: `#/quality?branch=${code}` }, "View in Data quality")));
  }).catch((err) => token === renderToken && fill(dq, errorBox(err)));
}

// ---------- Data quality ----------

async function pageQuality(params, token) {
  const state = {
    action: params.get("action") || "", rule: params.get("rule") || "", branch: params.get("branch") || "",
    batch: params.get("batch") || "", offset: Number(params.get("offset") || 0),
  };
  const update = (changes) => go("quality", { ...state, ...changes, offset: changes.offset ?? 0 });

  const tiles = el("div", { class: "grid cols-4" },
    tile("Rule failures", "—", "One row per record and failed rule"),
    tile("Rejected", "—", "Quarantined, kept out of Gold", { tone: "bad" }),
    tile("Flagged", "—", "Kept in Gold with a warning", { tone: "warn" }),
    tile("Rejected share", "—", "Rejected ÷ all rule failures"));
  const results = el("div", {}, loading());

  const seg = el("div", { class: "segmented" }, [["", "All"], ["REJECT", "Reject"], ["FLAG", "Flag"]].map(([v, l]) =>
    el("button", { type: "button", class: state.action === v ? "on" : null, onclick: () => update({ action: v }) }, l)));
  const ruleSel = el("select", { onchange: (e) => update({ rule: e.target.value }) }, el("option", { value: "" }, "All rules"), options(RULES, state.rule));
  const branchSel = el("select", { onchange: (e) => update({ branch: e.target.value }) }, el("option", { value: "" }, "All branches"), options(BRANCHES, state.branch));
  const batchIn = el("input", { value: state.batch, placeholder: "e.g. batch_001", size: 12 });

  fill(view,
    head("Data-quality exceptions", "Records the pipeline rejected or flagged, with the rule that failed. Rejected records are kept out of the KPIs; customer records appear only by hashed key."),
    tiles,
    el("div", { class: "card section" },
      el("form", { class: "filters", style: "margin-bottom:18px", onsubmit: (e) => { e.preventDefault(); update({ batch: batchIn.value.trim() }); } },
        el("div", { class: "field" }, "Action", seg),
        el("label", { class: "field" }, "Rule", ruleSel),
        el("label", { class: "field" }, "Branch", branchSel),
        el("label", { class: "field" }, "Batch", batchIn),
        el("button", { class: "btn", type: "submit" }, "Search")),
      results));

  // Headline totals (respect branch and batch, not action or rule)
  const scope = {};
  if (state.branch) scope.branch_code = state.branch;
  if (state.batch) scope.batch_id = state.batch;
  Promise.all([{}, { action: "REJECT" }, { action: "FLAG" }].map((x) =>
    api(`/exceptions?${new URLSearchParams({ ...scope, ...x, limit: 1 })}`))).then(([all, rej, flag]) => {
    if (token !== renderToken) return;
    const values = [nf.format(all.total), nf.format(rej.total), nf.format(flag.total), all.total ? fmt(rej.total / all.total, "ratio") : "–"];
    [...tiles.children].forEach((t, i) => { t.querySelector(".value").textContent = values[i]; });
  }).catch(() => {});

  const q = { limit: PAGE_SIZE, offset: state.offset, ...scope };
  if (state.action) q.action = state.action;
  if (state.rule) q.rule_id = state.rule;
  try {
    const res = await api(`/exceptions?${new URLSearchParams(q)}`);
    if (token !== renderToken) return;
    const last = Math.min(state.offset + res.items.length, res.total);
    fill(results,
      res.items.length ? table([
        { label: "Record", cls: "mono", key: "record_key" },
        { label: "Entity", render: (r) => r.entity.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) },
        { label: "Rule", cls: "mono", key: "rule_id" },
        { label: "Reason", key: "description" },
        { label: "Dimension", key: "dq_dimension" },
        { label: "Action", render: (r) => el("span", { class: `pill ${r.action}` }, r.action) },
        { label: "Branch", render: (r) => r.branch_code || "–" },
        { label: "Batch", cls: "mono", render: (r) => r.source_batch_id || "–" },
        { label: "Detected (UTC)", cls: "mono", render: (r) => fmtDateTime(r.detected_at) },
      ], res.items, { framed: true }) : el("p", { class: "empty" }, "No exceptions match these filters."),
      el("div", { class: "table-foot" },
        el("span", {}, res.total ? `Showing ${state.offset + 1}–${last} of ${nf.format(res.total)} · from GET ` : "From GET ", el("code", {}, "/exceptions")),
        el("div", { style: "display:flex;gap:8px" },
          el("button", { class: "btn-ghost", type: "button", disabled: state.offset === 0, onclick: () => update({ offset: Math.max(0, state.offset - PAGE_SIZE) }) }, "Previous"),
          el("button", { class: "btn-ghost", type: "button", disabled: last >= res.total, onclick: () => update({ offset: state.offset + PAGE_SIZE }) }, "Next"))));
  } catch (err) {
    if (token === renderToken) fill(results, errorBox(err));
  }
}

// ---------- Exposure graph ----------

async function pageExposure(params, token, id) {
  id = (id || "LA000225").toUpperCase();
  const input = el("input", { value: id, pattern: "LA\\d{6}", size: 12, required: true, title: "LA followed by 6 digits" });
  const body = el("div", {}, loading());

  fill(view,
    head("Connected exposure", "Follows the knowledge graph from one application to the applicant's household and every loan connected to it. Customers appear only by node key.",
      el("form", { class: "filters", onsubmit: (e) => { e.preventDefault(); go(`exposure/${input.value.trim().toUpperCase()}`); } },
        el("label", { class: "field" }, "Application ID", input),
        el("button", { class: "btn", type: "submit" }, "Find exposure"))),
    body);

  let res;
  try {
    res = await api(`/graph/applications/${encodeURIComponent(id)}/connected-exposure`);
  } catch (err) {
    if (token === renderToken) fill(body, errorBox(err));
    return;
  }
  if (token !== renderToken) return;

  const apps = res.applications;
  const applicant = apps.find((a) => a.application_id === res.application_id)?.customer_node;
  const customers = [...new Set(apps.map((a) => a.customer_node))].sort((a, b) => (a === applicant ? -1 : b === applicant ? 1 : 0));
  const late = apps.filter((a) => a.is_delinquent_30);
  const sum = (rows) => rows.reduce((t, r) => t + (r.outstanding_balance || 0), 0);

  const rows = [];
  for (const c of customers) {
    const loans = apps.filter((a) => a.customer_node === c);
    rows.push({ kind: "customer", node: c, details: `${c === applicant ? "Applicant" : "Same household"} · ${loans.length} application${loans.length === 1 ? "" : "s"}`, outstanding: sum(loans) });
    for (const l of loans) rows.push({ kind: "loan", ...l });
  }

  fill(body,
    el("div", { class: "grid cols-4" },
      tile("Household outstanding", fmt(res.total_outstanding, "EUR", { compact: false }), "Across all connected applications"),
      tile("Connected customers", nf.format(res.members), "Including the applicant"),
      tile("Connected applications", nf.format(apps.length), "Of every household member"),
      tile("Delinquent 30+", nf.format(res.delinquent_loans), late.length ? late.map((l) => l.application_id).join(", ") : "None", { tone: res.delinquent_loans ? "warn" : "" })),
    el("div", { class: "card section" },
      el("div", { class: "card-head" }, el("h2", {}, "Graph path"), el("span", { class: "src" }, "kg_nodes · kg_edges")),
      el("div", { class: "path" },
        el("span", { class: "step first" }, `Application ${res.application_id}`), el("span", { class: "arrow" }, "→"),
        el("span", { class: "step" }, `Customer ${short(nodeId(applicant))}`), el("span", { class: "arrow" }, "→"),
        el("span", { class: "step hh" }, "Household"), el("span", { class: "arrow" }, "→"),
        el("span", { class: "step" }, `${customers.length - 1} more customer${customers.length === 2 ? "" : "s"}`), el("span", { class: "arrow" }, "→"),
        el("span", { class: "step" }, `${apps.length - 1} more application${apps.length === 2 ? "" : "s"}`)),
      table([
        { label: "Node", render: (r) => r.kind === "customer"
          ? [el("span", { class: "elbow" }), el("span", { class: "pill node" }, "Customer"), " ", el("span", { class: "mono" }, short(nodeId(r.node)))]
          : el("span", { class: "indent-1" }, el("span", { class: "elbow" }), el("span", { class: "pill node" }, "Application"), " ",
            el("span", { class: "mono" }, r.application_id), r.application_id === res.application_id ? [" ", el("span", { class: "pill start" }, "Start")] : null) },
        { label: "Details", render: (r) => (r.kind === "customer" ? r.details : (r.status_code || "–").replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase())) },
        { label: "Outstanding", num: true, cls: "mono", render: (r) => fmt(r.kind === "customer" ? r.outstanding : r.outstanding_balance, "EUR", { compact: false }) },
        { label: "Status", render: (r) => (r.kind === "customer" ? "" : r.is_delinquent_30 ? el("span", { class: "pill late" }, "30+ days past due") : r.status_code === "APPROVED" ? el("span", { class: "status-ok" }, "Current") : "–") },
      ], rows, { framed: true, cls: "tree" }),
      el("div", { class: "table-foot" }, el("span", {}, "From GET ", el("code", {}, `/graph/applications/${res.application_id}/connected-exposure`)),
        el("span", {}, `Data as of ${fmtDate(res.as_of_date)}`))));
}

// ---------- Status ----------

async function pageStatus(params, token) {
  const health = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Service"), el("span", { class: "src" }, "GET /health")), loading());
  const ready = el("div", { class: "card" }, el("div", { class: "card-head" }, el("h2", {}, "Data"), el("span", { class: "src" }, "GET /ready")), loading());
  const connection = el("div", { class: "card section" }, el("div", { class: "card-head" }, el("h2", {}, "Your connection")),
    el("dl", { class: "facts" },
      el("dt", {}, "Credential"), el("dd", {}, useSignIn
        ? (auth.account() ? `Microsoft sign-in (${auth.account().username})` : "Not signed in")
        : (apiKey.value ? "API key" : "None")),
      el("dt", {}, "Kept"), el("dd", {}, "In this browser tab only (sessionStorage)"),
      el("dt", {}, "API reference"), el("dd", {}, el("a", { href: "/docs" }, "Swagger UI at /docs"))),
    el("div", { style: "margin-top:16px" }, useSignIn
      ? (auth.account()
        ? el("button", { class: "btn-ghost", type: "button", onclick: signOut }, "Sign out")
        : el("button", { class: "btn", type: "button", onclick: signIn }, "Sign in with Microsoft"))
      : el("button", { class: "btn-ghost", type: "button", onclick: () => askForKey() }, "Change API key")));
  fill(view, head("Status", "Is the API up, can it reach the Gold layer, and how fresh is the data."), el("div", { class: "grid cols-2" }, health, ready), connection);

  try {
    const h = await fetch("/health").then((r) => r.json());
    if (token !== renderToken) return;
    health.lastChild.replaceWith(el("dl", { class: "facts" },
      el("dt", {}, "Status"), el("dd", {}, h.status), el("dt", {}, "Environment"), el("dd", {}, h.environment),
      el("dt", {}, "Version"), el("dd", { class: "mono" }, h.version)));
  } catch { health.lastChild.replaceWith(errorBox(new ApiError(0, { code: "network_error", message: "The API could not be reached." }))); }

  if (!connected()) { // nothing to check without a credential, and a 401 here would only show the dialog
    ready.lastChild.replaceWith(el("p", { class: "muted" }, useSignIn ? "Sign in to check the data connection." : "Enter an API key to check the data connection."));
    return;
  }
  try {
    const r = await api("/ready");
    if (token !== renderToken) return;
    ready.lastChild.replaceWith(el("dl", { class: "facts" },
      el("dt", {}, "Warehouse"), el("dd", {}, "Reachable"), el("dt", {}, "Data as of"), el("dd", {}, fmtDate(r.as_of_date)),
      el("dt", {}, "Refreshed"), el("dd", { class: "mono" }, fmtDateTime(r.refreshed_at) + " UTC")));
  } catch (err) { if (token === renderToken) ready.lastChild.replaceWith(errorBox(err)); }
}

// ======================================================================================
// Router, header and credential dialog
// ======================================================================================

const PAGES = { overview: pageOverview, assistant: pageAssistant, branches: pageBranches, quality: pageQuality, exposure: pageExposure, status: pageStatus };

function go(path, params) {
  const qs = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== "" && v !== 0)).toString() : "";
  location.hash = `#/${path}${qs ? `?${qs}` : ""}`;
}

function route() {
  const [path, qs] = location.hash.replace(/^#\/?/, "").split("?");
  const [page, arg] = path.split("/");
  const name = PAGES[page] ? page : "overview";
  document.querySelectorAll(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.page === name));
  const token = ++renderToken;
  window.scrollTo(0, 0);
  if (!connected() && name !== "status") {
    if (useSignIn) {
      fill(view, head("Sign in", "Use your athtech Microsoft account. Team 2 members only."),
        el("div", { class: "card" },
          signInMessage ? el("div", { class: "alert error" }, signInMessage) : null,
          el("p", {}, "This dashboard reads everything through the Loan Analytics API, which accepts only signed-in Team 2 members on this environment."),
          el("button", { class: "btn", type: "button", onclick: signIn }, "Sign in with Microsoft")));
      return;
    }
    fill(view, head("Connect to the API", "Enter an API key to load the data."),
      el("div", { class: "card" }, el("p", {}, "This dashboard reads everything through the Loan Analytics API, and every data route needs a credential."),
        el("button", { class: "btn", type: "button", onclick: () => askForKey() }, "Enter API key")));
    askForKey();
    return;
  }
  Promise.resolve(PAGES[name](new URLSearchParams(qs || ""), token, arg && decodeURIComponent(arg)))
    .catch((err) => token === renderToken && fill(view, errorBox(err instanceof ApiError ? err : new ApiError(0, { message: String(err) }))));
}

async function loadHeader() {
  if (!connected()) { $("as-of").textContent = ""; return; }
  try {
    const r = await api("/ready");
    $("as-of").textContent = `Data as of ${fmtDate(r.as_of_date)}`;
  } catch (err) {
    $("as-of").textContent = err.code === "data_unavailable" ? "Warehouse unavailable" : "";
  }
}

function askForKey(message) {
  const dialog = $("key-dialog");
  fill($("key-message"), message ? el("div", { class: "alert error" }, message) : null);
  $("key-value").value = "";
  if (!dialog.open) dialog.showModal();
}

function initKeyDialog() {
  $("key-button").addEventListener("click", () => askForKey());
  $("key-cancel").addEventListener("click", () => $("key-dialog").close());
  $("key-form").addEventListener("submit", () => {
    apiKey.value = $("key-value").value.trim();
    store.set("apiKey", apiKey.value);
    portfolio = null;
    updateAuthUi();
    loadHeader();
    route();
  });
}

// The header shows either the API-key button (dev, local) or the Microsoft sign-in state (prod).
function updateAuthUi() {
  $("key-button").hidden = useSignIn;
  $("key-label").textContent = apiKey.value ? "Key set" : "Connect";
  $("signin-area").hidden = !useSignIn;
  if (!useSignIn) return;
  const account = connected() ? auth.account() : null;
  $("signin-button").hidden = Boolean(account);
  $("signed-in").hidden = !account;
  $("signout-button").hidden = !account;
  $("user-name").textContent = account ? account.name || account.username : "";
  $("signed-in").title = account ? account.username : "";
}

async function signIn() {
  signInMessage = "";
  try {
    await auth.signIn();
    signInRejected = false;
  } catch (err) {
    signInMessage = auth.describeError(err);
  }
  portfolio = null;
  updateAuthUi();
  loadHeader();
  route();
}

async function signOut() {
  try {
    await auth.signOut();
  } catch { /* the local session is cleared either way */ }
  signInRejected = false;
  signInMessage = "";
  portfolio = null;
  updateAuthUi();
  loadHeader();
  route();
}

async function main() {
  if (auth.inPopup) return; // the sign-in popup: MSAL in the opening window reads the response
  const health = await fetch("/health").then((r) => r.json()).catch(() => ({}));
  const badge = $("env-badge");
  badge.textContent = (health.environment || "").toUpperCase();
  badge.hidden = !health.environment;
  useSignIn = health.environment === "prod";
  if (useSignIn) {
    try {
      await auth.start();
    } catch (err) {
      signInMessage = auth.describeError(err);
    }
  }
  initKeyDialog();
  $("signin-button").addEventListener("click", signIn);
  $("signout-button").addEventListener("click", signOut);
  updateAuthUi();
  window.addEventListener("hashchange", route);
  loadHeader();
  route();
}

main();
