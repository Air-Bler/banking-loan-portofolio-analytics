# API contracts

Agreed before coding. The LLM pair and the frontend build against these, so change them only
after telling the team, in a pull request that updates this file.

## 1. Settings (environment variables only)

The names match `.env.example` and the assistant's settings (`api/assistant/`).
Locally they come from `.env` (git-ignored); on dev and prod from Key Vault.

| Variable | Value or use |
|---|---|
| `APP_ENV` | `local`, `dev` or `prod`; only `prod` switches on JWT |
| `API_KEYS` | comma-separated keys accepted on dev |
| `DATABRICKS_HOST` | `adb-7405613839659491.11.azuredatabricks.net` (no `https://`) |
| `DATABRICKS_WAREHOUSE_ID` | `8a4ccb32c82cc705` (warehouse `my1`); the HTTP path is `/sql/1.0/warehouses/<id>` |
| `DATABRICKS_TOKEN` | personal access tokens are disabled in the workspace: use an Entra token locally (see below) |
| `DATABRICKS_CATALOG` | `data2026acc123456` |
| `DATABRICKS_SCHEMA` | **`team2`** (not `loans`) |
| `AUTH_TENANT_ID` | Entra tenant that issues the JWTs (prod; from the cloud person) |
| `AUTH_AUDIENCE` | the API app registration's client ID (prod; from the cloud person) |
| `AZURE_OPENAI_*` | owned by the LLM pair (see section 6) |

Local Databricks token (lasts about an hour; `az login` once first):

```bat
for /f "delims=" %i in ('az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv') do @set DATABRICKS_TOKEN=%i
```

Check the connection with `uv run --env-file .env python scripts/check_db.py`.

### Authentication (`api/security.py`)

Every route except `/health` needs one of these; anything else is a 401 `unauthorized`.

| `APP_ENV` | Callers send | Checked against |
|---|---|---|
| `local`, `dev` | `X-API-Key: <key>` | one of `API_KEYS` (constant-time compare) |
| `prod` | `Authorization: Bearer <Entra ID access token>` | the tenant's published keys (`RS256` only), issuer `https://login.microsoftonline.com/<AUTH_TENANT_ID>/v2.0`, audience `<AUTH_AUDIENCE>` or `api://<AUTH_AUDIENCE>`, expiry (60 s leeway) |

Prod expects v2 access tokens: the app registration has `requestedAccessTokenVersion: 2`, exposes
`api://<client-id>`, and clients ask for the scope `api://<client-id>/.default`. If `AUTH_TENANT_ID`
or `AUTH_AUDIENCE` is empty, prod rejects every request (fails closed). An API key is never accepted
on prod. Keys and tokens are never logged.

## 2. Gold tables the API reads

Gold only. `team2` also holds `bronze_*` and `silver_*` tables with customer names, e-mails and
phone numbers: the API never reads them. Columns are listed in `docs/gold_schema.txt`.

| Table | Used by |
|---|---|
| `kpi_portfolio_monthly` | `/analytics/query`, `/branches/{branch_code}/summary` |
| `kpi_portfolio_summary` | `dti_band_share`, and checking all-branch totals |
| `dim_branch`, `dim_product` | branch and product codes for groupings |
| `fact_dq_exception` | `/exceptions` (never select `record_payload`) |
| `refresh_info` | `/ready`, and `as_of_date` in every response |
| `kg_nodes`, `kg_edges` | `/graph/applications/{application_id}/connected-exposure` |

## 3. Query module (`api/queries.py`)

Routes stay thin: each one validates input, calls one method and returns its result.

```python
class GoldRepository:
    def metric_catalogue(self) -> list[dict]: ...
    def query_metric(self, metric: str, group_by: str | None = None,
                     filters: dict | None = None, limit: int = 100) -> dict: ...
    def branch_summary(self, branch_code: str) -> dict | None: ...         # None -> 404
    def get_exceptions(self, rule_id=None, action=None, branch_code=None,
                       batch_id=None, limit=20, offset=0) -> dict: ...
    def connected_exposure(self, application_id: str) -> dict | None: ...  # None -> 404
    def refresh_info(self) -> dict: ...                                     # as_of_date, refreshed_at

def get_repository() -> GoldRepository: ...  # FastAPI dependency; tests swap in FakeRepository
```

Rules:

- Every method returns a JSON-ready dict that includes `source` and `as_of_date`.
- A method that looks up one item returns `None` when it doesn't exist.
- Every Databricks failure or timeout raises `DataUnavailable` (`api/errors.py`).
- `query_metric` accepts `date_from`, `date_to` and `branch_code` in `filters`.
- Groupings: `branch`, `product`, `month`, `year` or none. The monthly table has no DTI band,
  risk band or segment columns, so those groupings are not supported.
- `dti_band_share` comes from `kpi_portfolio_summary` only: any grouping or filter on it is a 422.
- Rates are never averaged: sum numerators and denominators, then divide.

**Open question for the LLM pair:** the assistant already has its own repository
(`src/loan_analytics/llm/repository.py`, `execute(ApprovedQuery)` through the Databricks SDK).
Do we keep both, or do the assistant tools call `api/queries.py`?

**Answer (LLM pair):** the assistant tools call `api/queries.py` only. The new assistant lives in
`api/assistant/` and writes no SQL; the legacy `src/loan_analytics/llm/` has been removed
(section 6).

## 4. Analytics request and response (values illustrative)

```json
POST /analytics/query
{"metric": "approval_rate", "group_by": "branch",
 "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"}, "limit": 100}
```

```json
200 OK
{"metric": {"name": "approval_rate", "label": "Approval rate", "unit": "ratio",
            "definition": "approved / (approved + rejected)"},
 "group_by": "branch",
 "filters": {"date_from": "2025-01-01", "date_to": "2025-12-31"},
 "rows": [{"group": "BR003", "value": 0.592, "numerator": 244, "denominator": 412}],
 "as_of_date": "2025-12-31",
 "source": "gold.kpi_portfolio_monthly",
 "correlation_id": "6f1c2a9e"}
```

Values are raw: amounts in EUR, rates as ratios (`0.592`, not `"59.2%"`), dates and times in
ISO 8601 UTC. Formatting is the frontend's job.

## 5. Error format (every error, including FastAPI's own validation errors)

```json
{"error": {"code": "not_found", "message": "Branch BR099 not found",
           "correlation_id": "6f1c2a9e", "details": []}}
```

| Status | `code` | When |
|---|---|---|
| 401 | `unauthorized` | missing or invalid API key or token |
| 404 | `not_found` | unknown branch, application or route |
| 405 | `method_not_allowed` | the route exists but not with that HTTP method |
| 422 | `validation_error` | bad body or parameter; `details` lists each field and message |
| 503 | `data_unavailable` | Databricks down or timed out |
| 503 | `assistant_unavailable` | the assistant isn't configured or Azure OpenAI is down |
| 500 | `internal_error` | anything unexpected; logged with the correlation ID, no stack trace in the response |

## 6. Assistant (`api/assistant/`, owned by the LLM pair)

The assistant answers portfolio questions in plain language, using only numbers that its tools read
through the query module (section 3). It writes no SQL and never reads Bronze or Silver.

### Entry point

```python
# api/assistant/__init__.py
def answer(question: str, repo: GoldRepository, llm: BaseChatModel) -> AssistantAnswer: ...
# raises DataUnavailable (Databricks down) or AssistantUnavailable (Azure OpenAI down)

# api/assistant/llm.py
def get_llm(settings: Settings = Depends(get_settings)) -> BaseChatModel: ...
# FastAPI dependency; raises AssistantUnavailable if an AZURE_OPENAI_* setting is missing
```

The route passes the repository and the model as dependencies, so tests swap in `FakeRepository`
and a scripted model: no Azure and no Databricks in CI.

### Tools (read-only, each calls one `GoldRepository` method)

| Tool | Calls |
|---|---|
| `get_portfolio_kpi` | `query_metric` (the 9 metrics, grouped by branch, product, month or year) |
| `get_dq_exceptions` | `get_exceptions` |
| `get_metadata` | `metric_catalogue` and `refresh_info` |
| `get_connected_exposure` | `connected_exposure` |

### Response (values illustrative)

```json
POST /assistant/query
{"question": "What was the approval rate by branch in 2025?"}
```

```json
200 OK
{"status": "answered",
 "answer": "BR003 approved 59.2% of decided applications in 2025 (244 of 412).",
 "evidence": [{"tool": "get_portfolio_kpi",
               "arguments": {"metric": "approval_rate", "group_by": "branch",
                             "date_from": "2025-01-01", "date_to": "2025-12-31", "limit": 20},
               "source": "gold.kpi_portfolio_monthly", "as_of_date": "2025-12-31",
               "result": {"rows": [{"group": "BR003", "value": 0.5921, "numerator": 244, "denominator": 412}]}}],
 "filters": {"metric": "approval_rate", "group_by": "branch", "date_from": "2025-01-01", "date_to": "2025-12-31"},
 "sources": ["gold.kpi_portfolio_monthly"],
 "measures": ["approval_rate"],
 "limitations": [],
 "trace": [{"round": 1, "tool": "get_portfolio_kpi",
            "arguments": {"metric": "approval_rate", "group_by": "branch",
                          "date_from": "2025-01-01", "date_to": "2025-12-31"},
            "status": "success"}],
 "model": "gpt-4.1-mini",
 "tool_rounds": 1,
 "correlation_id": "6f1c2a9e"}
```

Only `status`, `answer` and `limitations` come from the model. `evidence`, `filters`, `sources`,
`measures` and `trace` are built by code from the tool calls that actually ran; `trace` also lists
failed calls. Every number in `answer` is checked against the tool results: if one is not found,
the answer is replaced by the raw results and a limitation says why; a refusal that fails the check
shows the standard refusal instead. `correlation_id` is added by the route.

| `status` | When |
|---|---|
| `answered` | the tools returned data and the answer uses it |
| `refused` | an action, raw SQL, personal data, prompt injection or an off-topic question; refused before the model is called when the code can tell |
| `no_data` | the tools returned nothing usable (unknown ID, empty filter such as a KPI with no rows for an unknown branch, Databricks down during a tool call), or the model answered without any data |
| `incomplete` | the model was still asking for tools after 3 rounds |

Failures that are not an answer use the error format of section 5: `503 data_unavailable` when
Databricks is down before the model is asked, `503 assistant_unavailable` when an `AZURE_OPENAI_*`
setting is missing or Azure OpenAI still fails after the client's retries.

### Settings

| Variable | Value or use |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | the Azure OpenAI resource, e.g. `https://oai-loant2gk.openai.azure.com/` |
| `AZURE_OPENAI_DEPLOYMENT` | the model deployment name, e.g. `gpt-4.1-mini` |
| `AZURE_OPENAI_API_KEY` | secret: `.env` locally, Key Vault secret `azure-openai-api-key` on dev and prod |
| `AZURE_OPENAI_API_VERSION` | optional; default `2024-10-21` |

The client runs with `temperature=0`, a 30-second timeout and 2 retries (429 and 5xx, with backoff).

### Current state

The API route `/assistant/query` (`api/routers/assistant.py`) calls `answer()` and returns the
shape above; the frontend's Assistant page (`api/static/app.js`) and the Postman requests read it.
The legacy assistant (`src/loan_analytics/llm/`) and its tests have been removed.
