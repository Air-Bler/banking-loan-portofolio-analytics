import os

from databricks import sql

catalog = os.environ["DATABRICKS_CATALOG"]
schema = os.environ["DATABRICKS_SCHEMA"]

NEEDED = ["kpi_portfolio_monthly", "kpi_portfolio_summary", "fact_dq_exception",
          "dim_branch", "dim_product", "refresh_info", "kg_nodes", "kg_edges"]

with sql.connect(
    server_hostname=os.environ["DATABRICKS_HOST"],
    http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
    access_token=os.environ["DATABRICKS_TOKEN"],
    _retry_stop_after_attempts_count=3,
    _socket_timeout=30,
) as conn, conn.cursor() as cur:
    cur.execute(f"SHOW TABLES IN {catalog}.{schema}")
    existing = sorted(row[1] for row in cur.fetchall())

    print("All tables:")
    for t in existing:
        print("  ", t)

    print("\nTables the API needs:")
    for t in NEEDED:
        print("   OK     " if t in existing else "   MISSING", t)

    if "refresh_info" in existing:
        cur.execute(f"SELECT * FROM {catalog}.{schema}.refresh_info")
        print("\nrefresh_info:", cur.fetchall())