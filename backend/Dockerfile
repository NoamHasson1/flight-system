# The backend.
#
# Two stages: the first resolves dependencies, the second runs the application.
# The build tools, the lockfile resolution and the caches stay in the first and
# never reach the image that gets deployed -- a smaller image is a smaller
# attack surface and a faster deploy, and neither is worth arguing about.

# --- stage 1: dependencies ---------------------------------------------------

FROM python:3.12-slim-bookworm AS deps

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, application code second, so that editing a route does not
# reinstall the world. These two files change rarely; everything else changes
# constantly.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# --- stage 2: the application ------------------------------------------------

FROM python:3.12-slim-bookworm AS runtime

# A non-root user, because a process that does not need to write to the system
# should not be able to. If something does get in through the application, this
# is the difference between a bad day and a worse one.
RUN groupadd --system app && useradd --system --gid app --create-home app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=deps --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app app ./app

# Where uploaded documents land when LocalFileStorage is in use. Mount a volume
# here, or switch to object storage -- a container's filesystem does not
# survive a deploy, and a passenger's passport is not a thing to lose on a
# routine restart.
RUN mkdir -p /app/storage/uploads && chown -R app:app /app/storage

USER app

EXPOSE 8000

# The health endpoint rather than a bare port check: a process that is listening
# but cannot reach its database is not healthy, and the difference is exactly
# what an orchestrator needs to know before sending it traffic.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# Migrations are NOT run here. A container that migrates on startup will run
# several migrations at once the moment anything scales past one instance, and
# a half-applied schema is worse than a late deploy. Run them as a release step.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
