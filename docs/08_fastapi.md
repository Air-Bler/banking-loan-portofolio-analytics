# 08 · FastAPI service

The API is the only way into the Gold data for the frontend, the LLM assistant and the Postman tests.
It reads the governed Gold tables in `data2026acc123456.team2` on a Databricks SQL warehouse and never
touches Silver.

- Code: [`api/`](../api) · Tests: [`tests/api/`](../tests/api) · Postman: [`postman/`](../postman)
- Contracts agreed with the LLM pair and the cloud person: [`contracts.md`](contracts.md)
- OpenAPI (Swagger UI): `/docs` on every environment, e.g. `http://127.0.0.1:8000/docs` locally

## Routes

| Method | Path | Returns | Reads (Gold) | Auth |
|---|---|---|---|---|
| GET | `/health` | status, environment, version | nothing | none |
| GET | `/ready` | warehouse reachable, data as-of date | `refresh_info` | yes |
| POST | `/analytics/query` | one KPI, optionally grouped and filtered | `kpi_portfolio_monthly` (`kpi_portfolio_summary` for `dti_band_share`) | yes |
| GET | `/metadata/metrics` | the 9 metrics with their definitions | nothing (a list in code) | yes |
| GET | `/branches/{branch_code}/summary` | all KPIs for one branch, plus by product | `kpi_portfolio_monthly` | yes |
| GET | `/exceptions` | data-quality exceptions, paged | `fact_dq_exception`, `dim_branch` | yes |
| GET | `/graph/applications/{application_id}/connected-exposure` | household exposure of an application | `kg_nodes`, `kg_edges` | yes |
| POST | `/assistant/query` | the assistant's structured answer | via the LLM assistant's approved tools | yes |

Every route validates its input, calls one method of `GoldRepository` ([`api/queries.py`](../api/queries.py))
and returns its result. The LLM assistant's tools use the same Gold tables, so the API and the
assistant give the same numbers.

### The 9 metrics

All come from the additive parts in `kpi_portfolio_monthly` (by `month_key`, `branch_key`,
`product_key`). For any grouping, the API sums numerators and denominators first, then divides:
it never averages a rate. Rates are ratios (`0.592`, not `"59.2%"`), amounts are in EUR.

| Metric | Unit | Definition |
|---|---|---|
| `applications` | count | number of loan applications |
| `requested_amount` | EUR | total amount requested in the applications |
| `approval_rate` | ratio | approved / (approved + rejected) |
| `avg_decision_days` | days | days from submission to decision, averaged over decided applications |
| `high_dti_share` | ratio | applications with a DTI of 35% or more / applications with a DTI |
| `dti_band_share` | ratio | share of applications in each DTI band (whole portfolio only, from `kpi_portfolio_summary`) |
| `delinquency_rate_30` | ratio | active loans 30+ days past due / active loans |
| `outstanding_balance` | EUR | outstanding principal of the loans |
| `manual_review_rate` | ratio | applications sent to manual review / applications |

Groupings: `branch`, `product`, `month` (yyyyMM), `year`, or none. Filters: `date_from`, `date_to`
(by application month) and `branch_code`. `dti_band_share` takes no grouping or filter (422).
Branch key −1 is kept as an `UNKNOWN` group, so all-branch totals match `kpi_portfolio_summary`.

## Authentication

| `APP_ENV` | Accepted credential | Where it comes from |
|---|---|---|
| `local`, `dev` | `X-API-Key: <key>` header | `API_KEYS` (comma-separated); on dev from Key Vault secret `api-keys-dev` |
| `prod` | `Authorization: Bearer <token>` | an Entra ID access token for the API's app registration |

- Every route except `/health` needs a credential. A missing or wrong one returns 401 `unauthorized`.
- Keys are compared in constant time ([`api/security.py`](../api/security.py)). If `API_KEYS` is empty, every request is rejected.
- On prod the JWT is checked with PyJWT against the tenant's published signing keys (cached for an hour):
  signature (`RS256` only), issuer `https://login.microsoftonline.com/<AUTH_TENANT_ID>/v2.0`,
  audience `AUTH_AUDIENCE` (or `api://AUTH_AUDIENCE`), and expiry (60 s leeway). API keys are not
  accepted on prod.
- In `/docs`, use **Authorize** to set the key (or the bearer token on prod).
- The frontend at `/app` signs users in with Microsoft on prod, so nobody copies a token (see [Frontend](#frontend)).

## Error format

Every error, including FastAPI's own validation errors, has the same shape:

```json
{"error": {"code": "not_found", "message": "Branch BR099 not found",
           "correlation_id": "6f1c2a9e", "details": []}}
```

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | missing or invalid API key or token |
| 404 | `not_found` | unknown branch, application or route |
| 405 | `method_not_allowed` | the route exists, but not with that HTTP method |
| 422 | `validation_error` | bad body or parameter; `details` lists each field and message |
| 503 | `data_unavailable` | Databricks down or timed out |
| 503 | `assistant_unavailable` | the assistant isn't configured, or Azure OpenAI is down |
| 500 | `internal_error` | anything unexpected; logged with the correlation ID, no stack trace in the response |

Handlers: [`api/errors.py`](../api/errors.py). Raw exception text never reaches the response.

## Logging and correlation IDs

[`api/observability.py`](../api/observability.py):

- **Correlation ID.** A caller's `X-Correlation-ID` is reused if it is plain (letters, digits, `.`, `_`, `-`, up to 64 characters); otherwise the API generates one. It comes back in the `X-Correlation-ID` header of every response, in every error body, and in the `/analytics/query` body.
- **JSON logs.** One JSON object per line on stdout: time, level, logger, message and correlation ID.
  Each request logs its method, path, status and duration.
- **No secrets.** The logs never contain headers, query strings, bodies, keys, tokens or the assistant's question text. `API_KEYS` and `DATABRICKS_TOKEN` are `SecretStr`, so they print as `**********`.

## Outbound calls (Databricks)

[`api/db.py`](../api/db.py) opens one connection per request with `databricks-sql-connector`:

- at most 3 attempts instead of the connector's default 30, and a 30-second socket timeout;
- the connector's own retry and back-off handles warehouse rate limits (HTTP 429/503) inside those 3 attempts;
- every failure becomes `DataUnavailable`, which the API returns as 503 `data_unavailable`;
- values always go in as `:name` parameters. Table and column names come from fixed dicts, never from the request.

`/exceptions` is paged with `limit` (1–100, default 20) and `offset`, and returns `total`. It never
selects `record_payload`. For customer records it returns `SUBSTRING(SHA2(record_key, 256), 1, 16)`
instead of the raw customer ID.

## Examples (one per route)

The requests are the ones in the Postman collection. The response values are **illustrative**: the
shapes and field names are exact, but the numbers depend on the current Gold load. Run the
collection or `/docs` for live values. All examples send `X-API-Key` except `/health`.

**GET `/health`**: no key needed; used by the deploy smoke test. `version` is the short git SHA of the deployed commit.

```json
{"status": "ok", "environment": "dev", "version": "9b6a196"}
```

**GET `/ready`**

```json
{"status": "ready", "as_of_date": "2025-12-31", "refreshed_at": "2026-10-05T09:44:49Z"}
```

**POST `/analytics/query`**

```json
{"metric": "approval_rate", "group_by": "branch",
 "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"}, "limit": 100}
```

```json
{"metric": {"name": "approval_rate", "label": "Approval rate", "unit": "ratio",
            "definition": "approved / (approved + rejected)"},
 "group_by": "branch",
 "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"},
 "rows": [{"group": "BR003", "value": 0.592, "numerator": 244, "denominator": 412}],
 "as_of_date": "2025-12-31",
 "source": "gold.kpi_portfolio_monthly",
 "correlation_id": "6f1c2a9e"}
```

**GET `/metadata/metrics`**: no Databricks call.

```json
{"metrics": [{"name": "applications", "label": "Applications", "unit": "count",
              "definition": "number of loan applications"}, "... 9 in total"]}
```

**GET `/branches/BR003/summary`**

```json
{"branch_code": "BR003", "branch_name": "Kifisia",
 "kpis": {"applications": 412, "approval_rate": 0.592, "delinquency_rate_30": 0.031, "...": "every metric"},
 "by_product": [{"product_code": "PL-STD", "kpis": {"applications": 120, "approval_rate": 0.61, "...": "..."}}],
 "as_of_date": "2025-12-31", "source": "gold.kpi_portfolio_monthly"}
```

**GET `/exceptions?rule_id=CUS-04&limit=5`**

```json
{"items": [{"exception_key": 2, "rule_id": "CUS-04", "dq_dimension": "validity", "action": "FLAG",
            "description": "...", "entity": "customers", "record_key": "3f9a1c0b7d2e4a51",
            "branch_code": "BR003", "source_batch_id": "batch_002", "detected_at": "2026-10-05T09:41:00Z"}],
 "total": 37, "limit": 5, "offset": 0,
 "as_of_date": "2025-12-31", "source": "gold.fact_dq_exception"}
```

**GET `/graph/applications/LA000225/connected-exposure`**

```json
{"application_id": "LA000225", "members": 2,
 "applications": [{"customer_node": "customer:C00101", "application_id": "LA000225", "status_code": "APPROVED",
                   "outstanding_balance": 12500.0, "is_delinquent_30": 0}, "..."],
 "total_outstanding": 20800.5, "delinquent_loans": 1,
 "as_of_date": "2025-12-31", "source": "gold.kg_nodes, gold.kg_edges"}
```

On the real landing data, `LA000225` returns 6 applications across 2 household members. An
unknown ID returns 404.

**POST `/assistant/query`**

```json
{"question": "What was the approval rate by branch in 2025?"}
```

```json
{"status": "answered",
 "answer": "BR003 approved 59.2% of decided applications in 2025 (244 of 412).",
 "evidence": [{"tool": "get_portfolio_kpi",
               "arguments": {"metric": "approval_rate", "group_by": "branch",
                             "date_from": "2025-01-01", "date_to": "2025-12-31", "limit": 20},
               "source": "gold.kpi_portfolio_monthly", "as_of_date": "2025-12-31",
               "result": {"rows": [{"group": "BR003", "value": 0.5921, "numerator": 244, "denominator": 412}]}}],
 "filters": {"metric": "approval_rate", "group_by": "branch", "date_from": "2025-01-01", "date_to": "2025-12-31"},
 "sources": ["gold.kpi_portfolio_monthly"], "measures": ["approval_rate"], "limitations": [],
 "trace": [{"round": 1, "tool": "get_portfolio_kpi",
            "arguments": {"metric": "approval_rate", "group_by": "branch",
                          "date_from": "2025-01-01", "date_to": "2025-12-31"}, "status": "success"}],
 "model": "gpt-4.1-mini", "tool_rounds": 1, "correlation_id": "6f1c2a9e"}
```

The full shape and the four statuses (`answered`, `refused`, `no_data`, `incomplete`) are in
[`contracts.md`](contracts.md) section 6. Questions that ask for an action ("Delete all rejected
applications") or for raw SQL are refused with a 200, `"status": "refused"` and an empty `evidence`
list. The model is not called for them.

## Executable examples: Postman

[`postman/loan-api.postman_collection.json`](../postman/loan-api.postman_collection.json) has 20
requests in 4 folders (Platform, Data, Errors, Assistant), each with tests on the status and at
least one field. The collection has two variables: `baseUrl` and `apiKey`. No key is committed.
Full instructions: [`postman/README.md`](../postman/README.md).

```bash
npx newman run postman/loan-api.postman_collection.json \
  --env-var baseUrl=http://127.0.0.1:8000 --env-var apiKey=local-dev-key --timeout-request 60000
```

## How to run locally

1. Install the dependencies: `uv sync`
2. Copy `.env.example` to `.env` (git-ignored) and set at least:

   ```
   APP_ENV=local
   API_KEYS=local-dev-key
   DATABRICKS_HOST=adb-7405613839659491.11.azuredatabricks.net
   DATABRICKS_WAREHOUSE_ID=8a4ccb32c82cc705
   DATABRICKS_CATALOG=data2026acc123456
   DATABRICKS_SCHEMA=team2
   ```

3. Get a Databricks token. Personal access tokens are disabled, so use an Entra token, which lasts about an hour (`cmd`):

   ```bat
   az login
   for /f "delims=" %i in ('az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv') do @set DATABRICKS_TOKEN=%i
   ```

4. Start the API: `uv run --env-file .env uvicorn api.main:app --reload`
5. Open `http://127.0.0.1:8000/docs` and click **Authorize** with `local-dev-key`.

Without a token, `/health` and `/metadata/metrics` still work. The data routes and `/ready` answer
503 `data_unavailable`. For the assistant, also set the `AZURE_OPENAI_*` variables; without them
it answers 503 `assistant_unavailable`.

Before every push: `uv run ruff check . && uv run pytest -q`.

## Frontend

A dashboard is served by the same app at **`/app`** (and `/` redirects there). It lives in
[`api/static/`](../api/static): plain HTML, CSS and JavaScript, with no build step, no new
dependencies and no CDN. It ships in the same container, so every deploy updates it.

| Page | What it shows | Calls |
|---|---|---|
| Overview | 8 KPI tiles, applications per year (per month inside one year), DTI bands, a by-branch table; period and branch filters | `POST /analytics/query` |
| Assistant | chat with the assistant: a badge from `status`, the answer, one evidence box per tool call (tool, Gold table, as-of date, values), filters, sources and limitations, and a "Show trace" button with every tool call in order, failed ones included | `POST /assistant/query` |
| Branches | one branch's KPIs against the portfolio, the application funnel, applications/approval/delinquency by product, its data-quality exception count | `GET /branches/{code}/summary`, `POST /analytics/query`, `GET /exceptions` |
| Data quality | totals (rejected, flagged), filters by action, rule, branch and batch, paged table | `GET /exceptions` |
| Exposure graph | household outstanding, connected customers and applications, the graph path and a customer → application tree | `GET /graph/applications/{id}/connected-exposure` |
| Status | service version and environment, warehouse reachability and data freshness | `GET /health`, `GET /ready` |

- **Credential.** The page holds no data and loads without a key. It reads `environment` from `/health`:
  - **prod: Sign in with Microsoft.** [`api/static/auth.js`](../api/static/auth.js) uses MSAL.js (`@azure/msal-browser` 3.30.0, vendored in `api/static/vendor/`, no CDN) with the Team 2 Entra app. The values are client ID `ea9e7159-…`, the athtech tenant, and scope `api://ea9e7159-…/access_as_user`. Sign-in and sign-out use popups that return to the site root, which redirects to `/app/` and keeps the response fragment. Every call sends `Authorization: Bearer <token>`. MSAL renews the token silently, so the session outlives the one-hour token. A 401 shows the sign-in button again, and AADSTS50105 shows "Only Team 2 members can sign in."
  - **dev and local: API key.** The key is asked for once per tab and sent as `X-API-Key`. A 401 reopens the dialog.
  - Both live in `sessionStorage`, so they are forgotten when the tab closes. The API side (`api/security.py`) and the settings are unchanged.
- **Errors** appear in the agreed format, with the code and correlation ID. While `AZURE_OPENAI_*` is not set, the Assistant shows "not available on this environment", and the other pages keep working.
- **Formatting** happens only in the browser (ratios as %, EUR amounts, dates); the API returns raw values.
- **Rates are never averaged in the browser.** The by-branch table and the funnel use the API's own grouped values and numerators/denominators.
- **Data is inserted with `textContent`**, never as HTML.
- **Not shown, because the API does not expose it:**
  - open-installment ageing
  - risk-band mix per branch
  - per-rule exception counts
  - a product filter (the API can group by product, not filter)
- **Tests:** `tests/api/test_frontend.py` checks that the page is served without a key, that `/` redirects to it, that it does not open the data routes, and that it stays out of the OpenAPI schema.

## Test evidence

**pytest** (`uv run pytest -q`, also run by CI on every push, with results uploaded as `test-results.xml`):
**338 passed** (140 API tests, 197 assistant tests in `tests/assistant/`, 1 health test).

| File | Tests | Covers |
|---|---|---|
| `test_analytics.py` | 22 | every metric accepted, grouping, DTI band share, 422 on bad input, the metric catalogue |
| `test_queries.py` | 13 | the SQL `GoldRepository` builds: rates are summed and never averaged, values are parameters, no `record_payload`, customer keys are hashed |
| `test_exceptions.py` | 10 | filters, paging, 422, 503 |
| `test_branches.py`, `test_graph.py` | 4 + 4 | 200, 404, 422, 503 |
| `test_ready.py` | 2 | ready, and 503 when Databricks is down |
| `test_assistant.py` | 12 | grounded answer, refusal without calling the model, 422, not configured / model down → 503 `assistant_unavailable`, Databricks down → 503 `data_unavailable`, 401, question never logged |
| `test_settings.py` | 3 | the `AZURE_OPENAI_*` settings: read from the environment, default API version, key never printed |
| `test_auth.py` | 17 | 401 on every protected route, key list, `/health` open |
| `test_jwt.py` | 24 | prod: signature, issuer, audience, expiry, algorithm, missing token |
| `test_errors.py` | 7 | the error format for 404, 405, 422, 500 and 503; no stack trace |
| `test_correlation.py` | 7 | ID in and out on 200/401/404/500/503, unsafe IDs replaced, JSON logs without secrets |
| `test_db.py` | 7 | capped retries and timeout; connector failure → 503 through the real repository |
| `test_frontend.py` | 4 | `/app` served without a key, `/` redirects, data routes stay protected, not in OpenAPI |

**Newman** (from [`postman/README.md`](../postman/README.md)):

| Where | Folders | Requests | Assertions | Failed |
|---|---|---|---|---|
| local, real Gold | Platform, Data, Errors | 17 | 52 | 0 |
| dev | Platform, Data, Errors | 17 | 52 | 0 |
| local, `FakeRepository` and the real Azure OpenAI model | Assistant | 4 | 12 | 0 |

## What is mocked

The brief allows mocks only when they are documented. These are the only ones:

| Mock | Where | Stands in for | Why |
|---|---|---|---|
| `FakeRepository` | [`tests/api/fakes.py`](../tests/api/fakes.py) | `GoldRepository` (Databricks) | CI has no warehouse. A few hand-made rows in the real Gold formats; `fail=True` simulates an outage |
| `sql.connect` monkeypatch | `tests/api/test_db.py`, `test_queries.py` | the Databricks connector | test the retry and timeout caps and the 503 path without a warehouse |
| `ScriptedLLM` | [`tests/assistant/scripted_llm.py`](../tests/assistant/scripted_llm.py) | Azure OpenAI | the assistant and `/assistant/query` tests replay fixed model replies; no network. `tests/llm_helpers.py` is used only by the legacy assistant's tests and goes with them |
| Test key pair, fake JWKS | `tests/api/test_jwt.py` | Entra ID signing keys | sign test tokens locally; nothing reaches Entra ID |

All of these exist only in `tests/`. The running API, locally and on dev and prod, always uses the
real Databricks warehouse, Azure OpenAI and Entra ID. The response values in the
[Examples](#examples-one-per-route) section above are illustrative, as noted there.
