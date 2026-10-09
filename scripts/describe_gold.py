import os
from databricks import sql

catalog = os.environ["LOAN_CATALOG"]
schema = os.environ["LOAN_SCHEMA"]

TABLES = ["refresh_info", "kpi_portfolio_monthly", "kpi_portfolio_summary",
          "dim_branch", "dim_product", "fact_dq_exception", "kg_nodes", "kg_edges"]

lines = []
with sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=os.environ["DATABRICKS_HTTP_PATH"],
    access_token=os.environ["DATABRICKS_TOKEN"],
    _retry_stop_after_attempts_count=3,
    _socket_timeout=30,
) as conn, conn.cursor() as cur:
    for table in TABLES:
        cur.execute(f"DESCRIBE TABLE {catalog}.{schema}.{table}")
        lines.append(f"\n## {table}")
        for col_name, data_type, *_ in cur.fetchall():
            if not col_name or col_name.startswith("#"):
                break
            lines.append(f"  {col_name:35} {data_type}")

        cur.execute(f"SELECT COUNT(*) FROM {catalog}.{schema}.{table}")
        lines.append(f"  -> {cur.fetchone()[0]} rows")

output = "\n".join(lines)
print(output)
os.makedirs("docs", exist_ok=True)
with open("docs/gold_schema.txt", "w", encoding="utf-8") as f:
    f.write(output)
print("\nSaved to docs/gold_schema.txt")