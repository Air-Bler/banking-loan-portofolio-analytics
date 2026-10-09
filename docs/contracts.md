# API contracts

Agreed before coding. The LLM pair and the frontend build against these, so change them only
after telling the team, in a pull request that updates this file.

## 1. Settings (environment variables only)

The names match `.env.example` and the LLM pair's code (`src/loan_analytics/llm/settings.py`).
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
| `AUTH_TENANT_ID` | Entra tenant that issues the JWTs (from the cloud person) |
| `AUTH_AUDIENCE` | the API's app registration ID (from the cloud person) |
| `AZURE_OPENAI_*` | owned by the LLM pair |

Local Databricks token (lasts about an hour; `az login` once first):

```bat
for /f "delims=" %i in ('az account get-access-token --resource 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d --query accessToken -o tsv') do @set DATABRICKS_TOKEN=%i
```

Check the connection with `uv run --env-file .env python scripts/check_db.py`.

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
| 422 | `validation_error` | bad body or parameter; `details` lists each field and message |
| 503 | `data_unavailable` | Databricks down or timed out |
| 503 | `assistant_unavailable` | the assistant isn't wired in or Azure OpenAI is down |
| 500 | `internal_error` | anything unexpected; logged with the correlation ID, no stack trace in the response |
