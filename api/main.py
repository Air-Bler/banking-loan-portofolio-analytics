import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.errors import register_error_handlers
from api.models import ReadyResponse
from api.observability import configure_logging, register_correlation_id
from api.queries import GoldRepository, get_repository
from api.routers import analytics, assistant, branches, exceptions, graph
from api.security import require_auth

configure_logging()
app = FastAPI(title="Loan Portfolio Analytics API")
register_error_handlers(app)
register_correlation_id(app)
protected = [Depends(require_auth)]  # every route except /health
VERSION_FILE = Path(__file__).with_name(
    "version.txt"
)  

app.include_router(analytics.router, dependencies=protected)
app.include_router(branches.router, dependencies=protected)
app.include_router(exceptions.router, dependencies=protected)
app.include_router(graph.router, dependencies=protected)
app.include_router(assistant.router, dependencies=protected)


@app.get("/health")
def health() -> dict:
    version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "local"
    return {
        "status": "ok",
        "environment": os.getenv("APP_ENV", "local"),
        "version": version,
    }


@app.get("/ready", response_model=ReadyResponse, dependencies=protected)
def ready(repository: GoldRepository = Depends(get_repository)) -> dict:
    """The warehouse answers and the Gold data has an as-of date; 503 data_unavailable otherwise."""
    info = repository.refresh_info()
    return {"status": "ready", "as_of_date": info["as_of_date"], "refreshed_at": info["refreshed_at"]}


# The frontend (phase 9): static files, no data in them. Every call they make sends the user's key.
app.mount("/app", StaticFiles(directory=Path(__file__).with_name("static"), html=True), name="app")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/app/")
