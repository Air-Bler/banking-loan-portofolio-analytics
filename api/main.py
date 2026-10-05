import os
from pathlib import Path

from fastapi import FastAPI

app = FastAPI(title="Loan Portfolio Analytics API")
VERSION_FILE = Path(__file__).with_name(
    "version.txt"
)  # written by CI: the commit being run


@app.get("/health")
def health() -> dict:
    version = VERSION_FILE.read_text().strip() if VERSION_FILE.exists() else "local"
    return {
        "status": "ok",
        "environment": os.getenv("APP_ENV", "local"),
        "version": version,
    }
