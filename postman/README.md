# Postman collection

`loan-api.postman_collection.json` has a request for every route, each with a test on the status
and at least one field. Every response is also checked for an `X-Correlation-ID` header.

| Folder | Requests | Needs |
|---|---|---|
| Platform | `/health`, `/ready`, `/ready` without a key or with a wrong key (401) | - |
| Data | analytics (approval rate by branch, outstanding balance by year, DTI band share), metric catalogue, branch summary, exceptions, connected exposure | Databricks |
| Errors | unknown metric, grouping on DTI band share, malformed branch code (422); unknown branch, application, route (404) | - |
| Assistant | a KPI and a breakdown question that must be answered from Gold data (`status` answered, `evidence` not empty), an action request that must be refused, an empty question (422) | `AZURE_OPENAI_*` |

## Variables

- `baseUrl`: `http://127.0.0.1:8000` locally, the dev URL in the pipeline.
- `apiKey`: empty in the file. Pass it at run time, never commit a real key. In the Postman app,
  set it as the *current value* only.

## Run

Local (start the API first with `uv run --env-file .env uvicorn api.main:app`, `API_KEYS` set in `.env`):

```bash
npx newman run postman/loan-api.postman_collection.json --env-var baseUrl=http://127.0.0.1:8000 --env-var apiKey=local-dev-key --timeout-request 60000
```

Dev (the key is in Key Vault as `api-keys-dev`; dev sleeps when idle, so the first call can take 30 s):

```bash
export DEV_API_KEY=$(az keyvault secret show --vault-name kv-loant2gk -n api-keys-dev --query value -o tsv)
npx newman run postman/loan-api.postman_collection.json --env-var baseUrl=https://ca-loant2gk-dev.livelyplant-ec747e62.germanywestcentral.azurecontainerapps.io --env-var apiKey=$DEV_API_KEY --timeout-request 60000
```

Until `AZURE_OPENAI_*` is set on an environment, the assistant answers 503 there: add
`--folder Platform --folder Data --folder Errors` to skip the Assistant folder.

Prod takes an Entra ID bearer token instead of an API key, so this collection targets local and dev.

## Last runs

| Where | Folders | Requests | Assertions | Failed |
|---|---|---|---|---|
| local, real Gold | Platform, Data, Errors | 17 | 52 | 0 |
| dev | Platform, Data, Errors | 17 | 52 | 0 |
| local, `FakeRepository` and the real Azure OpenAI model | Assistant | 4 | 12 | 0 |

On dev, the pipeline's `api-tests` job runs every folder after each deploy.
