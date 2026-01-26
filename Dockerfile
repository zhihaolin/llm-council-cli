FROM python:3.10-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock README.md ./

# Install dependencies only (not the project itself)
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code
COPY backend/ backend/
COPY cli/ cli/

# Install the project package
RUN uv sync --frozen --no-dev

# Set entrypoint
ENTRYPOINT ["uv", "run", "llm-council"]
