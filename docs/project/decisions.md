# Project decisions

The main technical and process decisions, with the reason and the trade-off we accepted.
Newest last.

| # | Decision | Why | Trade-off |
|---|---|---|---|
| 1 | **Lakeflow Declarative Pipeline in SQL** for Bronze, Silver and Gold | The pattern taught in class; streaming tables, expectations and AUTO CDC give incremental loads and data-quality counts without extra code | Parts of it (Auto Loader, expectations) only run inside Databricks, so the local Spark test covers the SQL logic, not those features |
| 2 | **Quarantine instead of dropping** bad records: 37 rules, REJECT or FLAG, every hit in `fact_dq_exception` | Every rejected record stays traceable to a rule, a batch and a branch, which the Data quality page and the assistant both show | Counts and amounts in Gold are about 3% lower than the raw files, by design |
| 3 | **Knowledge graph as two Gold tables** (`kg_nodes`, `kg_edges`) queried by the API and the assistant | No extra service or licence; the graph lives next to the rest of the governed data | No graph database or graph query language; paths are fixed joins |
| 4 | **Azure Container Apps** for dev and prod, one image for both | The same tested image is promoted from dev to prod; revisions make rollback a redeploy; apps scale to zero when idle | A cold start of about 20 s after idle time (`infra/demo_mode.sh` keeps one replica for the presentation) |
| 5 | **Prod behind a GitHub approval issue** (`trstringer/manual-approval`) | Environment required reviewers were not available on the repository, and every prod deploy still needs a person to say `approve` | The approval waits 60 minutes, then the run times out and has to be re-run |
| 6 | **Newman gate before prod**: the whole Postman collection runs against dev on every merge | A broken route or assistant answer stops before prod | Each merge takes a few minutes longer |
| 7 | **Rollback by re-running an earlier `deploy-prod` job** | Every image is tagged with its commit and kept in the registry; rehearsed in 51 s | Data changes in Databricks are not rolled back this way |
| 8 | **Secrets only in Key Vault (RBAC)**, read by each app's managed identity; team access granted per secret | No secret in the repo, the pipeline or plain app settings; each pair sees only the secrets it needs | More role assignments to manage |
| 9 | **Prod: Microsoft Entra ID tokens only. Dev and local: an API key** | Prod data is reachable only by assigned team members (role `Loan.Read`, assignment required); dev stays easy to test and to run Newman against | Two authentication paths to test; prod never accepts the key, even in an emergency (use dev) |
| 10 | **"Sign in with Microsoft" on the dashboard** (MSAL.js, vendored, no CDN) | Team members use their athtech account instead of copying tokens; silent renewal keeps the session open | Sign-in uses pop-ups, so a browser that blocks them shows a message |
| 11 | **Databricks access with the instructor's token for now** | The only working credential in the course workspace | In production this would be a service principal with read access to Gold only |
| 12 | **No ML model** | Decided by the team on 11 Oct; no ML code or packages are in `main` | No prediction features |
| 13 | **Assistant answers only through four read-only tools, with evidence on every answer** | Numbers come from Gold, never from the model; the grounding check flags numbers that are not in the tool results | Questions outside the four tools (e.g. risk band or segment breakdowns) are answered as not supported |
| 14 | **Separate Azure OpenAI deployments for prod and evaluation** (14 Oct) | Evaluation runs were using up the shared limit and prod answers took 20 s; logs showed the 429s | Two deployments to keep in sync (`infra/openai_setup.sh`) |
| 15 | **`main` protected** (ruleset PROTECT-MAIN, 14 Oct): pull request, one approving review, green lint, test and build | Nothing reaches `main`, and so dev and prod, without a second person and passing checks | Authors cannot approve their own pull requests |
| 16 | **Code freeze on Thu 15 Oct at noon**, tag `v1.0` | The presentation runs on a known, rehearsed version | Fixes after the freeze only for something broken |
