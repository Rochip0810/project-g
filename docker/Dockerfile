# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.11.32-python3.13-trixie-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN groupadd --system --gid 10001 projectg \
    && useradd \
        --system \
        --uid 10001 \
        --gid projectg \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        projectg

COPY pyproject.toml uv.lock README.md .python-version ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev \
    && chown -R projectg:projectg /app

USER projectg

EXPOSE 8000

CMD ["project-g"]
