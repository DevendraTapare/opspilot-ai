FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.23@sha256:d0a0a753ab981624b49c97abc98821c1c09f4ca69d1ef5cee69c501be3d88479 /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS runtime
RUN uv sync --frozen --no-dev --no-install-project
COPY opspilot ./opspilot
COPY migrations ./migrations
COPY alembic.ini ./
RUN useradd --uid 10001 --create-home opspilot
USER opspilot
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "opspilot.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--log-config", "/app/opspilot/uvicorn-logging.json"]

FROM base AS test
RUN uv sync --frozen --no-install-project
COPY opspilot ./opspilot
COPY migrations ./migrations
COPY alembic.ini ./
COPY tests ./tests
COPY scripts ./scripts
COPY reviews ./reviews
COPY evaluations ./evaluations
RUN mkdir -p /app/artifacts
ENV PATH="/app/.venv/bin:$PATH"
CMD ["pytest", "-q"]
