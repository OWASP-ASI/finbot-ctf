# ── Base stage: install dependencies ──────────────────────────────────
FROM python:3.13-slim-bookworm AS base

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install dependencies first (cached unless pyproject.toml / uv.lock change)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy application source
COPY . .
RUN uv sync --frozen --no-dev

# Persistent data directories
RUN mkdir -p data uploads cache/share_cards

# Put the venv on PATH so we can use installed packages directly
ENV PATH="/app/.venv/bin:$PATH"

# ── App target (default): lean image, no Playwright ──────────────────
FROM base AS app

RUN useradd --create-home --shell /bin/bash finbot && \
    chown -R finbot:finbot /app
USER finbot

EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn finbot.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 300 --graceful-timeout 60"]

# ── Full target: includes Playwright + Chromium for OG image rendering
FROM base AS app-full

ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright
RUN playwright install --with-deps chromium

RUN useradd --create-home --shell /bin/bash finbot && \
    chown -R finbot:finbot /app
USER finbot

EXPOSE 8000
ENTRYPOINT ["sh", "docker/entrypoint.sh"]
CMD ["sh", "-c", "gunicorn finbot.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-3} --timeout 300 --graceful-timeout 60"]
