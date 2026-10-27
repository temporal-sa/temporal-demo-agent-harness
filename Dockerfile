FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv

# The harness comes from a git commit (see pyproject.toml), and uv needs git to fetch it.
# Only the resulting .venv goes into the runtime image.
FROM python:3.13-slim AS deps
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY --from=deps /app/.venv ./.venv
COPY agent_harness_demo ./agent_harness_demo
COPY --from=ui /agent_harness_demo/ui_dist ./agent_harness_demo/ui_dist
# Compose mounts a shared payload volume here; hosted pods use S3 instead.
RUN mkdir /payloads && chown 10001:10001 /payloads

ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "agent_harness_demo"]
CMD ["web"]
