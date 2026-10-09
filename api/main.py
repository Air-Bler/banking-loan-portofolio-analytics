import os
from pathlib import Path

from fastapi import FastAPI

from api.errors import register_error_handlers
from api.routers import analytics, assistant, branches, exceptions, graph

app = FastAPI(title="Loan Portfolio Analytics API")
register_error_handlers(app)
VERSION_FILE = Path(__file__).with_name(
    "version.txt"
)  

app.include_router(analytics.router)
app.include_router(branches.router)
app.include_router(exceptions.router)
app.include_router(graph.router)
app.include_router(assistant.router)


@app.get("/health")
def health() -> dict:
    version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "local"
    return {
        "status": "ok",
        "environment": os.getenv("APP_ENV", "local"),
        "version": version,
    }