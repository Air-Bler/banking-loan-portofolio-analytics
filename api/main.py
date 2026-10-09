import os
from pathlib import Path

from fastapi import Depends, FastAPI

from api.errors import register_error_handlers
from api.models import ReadyResponse
from api.queries import GoldRepository, get_repository
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


@app.get("/ready", response_model=ReadyResponse)
def ready(repository: GoldRepository = Depends(get_repository)) -> dict:
    """The warehouse answers and the Gold data has an as-of date; 503 data_unavailable otherwise."""
    info = repository.refresh_info()
    return {"status": "ready", "as_of_date": info["as_of_date"], "refreshed_at": info["refreshed_at"]}
