FROM python:3.10-slim

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy source code
COPY backend/ backend/
COPY cli/ cli/

# Set entrypoint
ENTRYPOINT ["uv", "run", "llm-council"]
