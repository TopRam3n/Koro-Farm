# KoroFarm backend image: one image, three uses (API, supply-exception worker, one-off operations).
#   API:        uvicorn src.backend.app.main:app ...           (compose service "api")
#   Worker:     python -m src.backend.app.worker               (compose service "worker")
#   Operations: python -m alembic -c src/backend/alembic.ini upgrade head, check_staging, provision_staging
# Build from the repository root:  docker build -f deploy/backend.Dockerfile -t korofarm-backend .
# No secret is baked in: every credential arrives as an environment variable at run time.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# postgresql-client provides pg_dump / pg_restore for the documented backup procedure.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY src/backend/pyproject.toml src/backend/pyproject.toml
COPY src/backend/app src/backend/app
COPY src/backend/alembic src/backend/alembic
COPY src/backend/alembic.ini src/backend/alembic.ini
COPY src/backend/scripts src/backend/scripts
# The model SDK is installed so staging can run the synthetic provider evaluation; the provider stays off unless
# AGENT_MODEL_PROVIDER is set, never in production, and in staging only with AGENT_MODEL_STAGING_APPROVAL.
RUN pip install "./src/backend[model]"

RUN useradd --system --uid 10001 --home-dir /srv korofarm && chown -R korofarm /srv
USER korofarm

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "src.backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]
