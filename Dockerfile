  FROM python:3.14-slim
  COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

  WORKDIR /app
  COPY pyproject.toml uv.lock README.md ./
  RUN uv sync --locked --no-dev --no-install-project      # third-party runtime packages (cached layer)
  COPY src ./src
  COPY api ./api
  RUN uv sync --locked --no-dev                           # installs our own package (loan_analytics)

  ENV PATH="/app/.venv/bin:$PATH"
  EXPOSE 8000
  CMD ["gunicorn", "-w", "2", "-k", "uvicorn_worker.UvicornWorker", "-b", "0.0.0.0:8000", "api.main:app"]