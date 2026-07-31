FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# git and the docker CLI are only needed by the livingbot-update-server command,
# which pulls the repo and redeploys via the host's docker daemon (mounted socket).
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    docker.io \
    docker-compose-v2 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

CMD ["livingbot-admin"]
