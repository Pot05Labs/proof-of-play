# Stage 1: build the web app
FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the API, serving the built web app on the same origin
FROM python:3.13-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist ./web/dist
ENV POP_WEB_DIST=/app/web/dist PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "pop.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
