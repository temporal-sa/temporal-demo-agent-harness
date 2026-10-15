FROM node:22-slim AS ui
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY agent_harness_demo ./agent_harness_demo
COPY --from=ui /agent_harness_demo/ui_dist ./agent_harness_demo/ui_dist
# Compose mounts a shared payload volume here; hosted pods use S3 instead.
RUN mkdir /payloads && chown 10001:10001 /payloads

ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["python", "-m", "agent_harness_demo"]
CMD ["web"]
