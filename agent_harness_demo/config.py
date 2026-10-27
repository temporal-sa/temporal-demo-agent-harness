"""Runtime settings shared by the web and worker processes, read from the environment."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from temporalio.client import Client, Plugin
from temporalio.converter import ExternalStorage
from temporalio.envconfig import ClientConfig

from temporal_agent_harness.harness.redis_event_stream import RedisEventStream
from temporal_agent_harness.utils.large_payload import local_payload_storage, s3_payload_storage

REGISTRY_PATH = Path(__file__).parent / "ziggy" / "agents.toml"

# The catalog injects a per-workspace queue (`agent-harness-<workspace>`) into every
# component through this variable; see `crashable.taskQueueEnv` in the registry's
# projects/demo/agent-harness.yaml.
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "agent-harness")

# Agents wait for their next message indefinitely, so an abandoned session is closed by
# Temporal when this runs out. Subagents close with their parent.
SESSION_TIMEOUT = timedelta(hours=float(os.environ.get("SESSION_TIMEOUT_HOURS", "24")))

# Agent events (turn lifecycle, reply deltas, tool calls, approvals, trip board changes) are
# streamed through Redis rather than the agent Workflow, so they cost no Signals, Updates, or
# history. The worker writes them and the web process reads them, so both use this URL.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

# One instance per process: the worker's plugin runs a single writer for it.
EVENT_STREAM = RedisEventStream(REDIS_URL)


def temporal_ui_url(namespace: str) -> str:
    """Base URL for this namespace in the Temporal UI, for links from the demo view."""
    if url := os.environ.get("TEMPORAL_UI_URL"):
        return url.rstrip("/")
    if os.environ.get("TEMPORAL_ADDRESS", "").endswith(".tmprl.cloud:7233"):
        return f"https://cloud.temporal.io/namespaces/{namespace}"
    return f"http://localhost:8233/namespaces/{namespace}"


async def payload_storage() -> ExternalStorage:
    """Where the harness offloads payloads above ~1.5 MB (sandbox snapshots, long histories).

    Every process must use the same backend. Hosted pods share an S3 bucket; Compose shares
    a volume. Objects are keyed by content hash, so workspaces sharing a bucket can't collide.
    """
    if bucket := os.environ.get("PAYLOAD_BUCKET"):
        return await s3_payload_storage(bucket=bucket)
    return local_payload_storage(base_dir=os.environ.get("PAYLOAD_DIR"))


async def connect(plugins: list[Plugin]) -> Client:
    # Address, namespace, and credentials come from TEMPORAL_* variables only, never from a
    # developer's temporal.toml, whose default profile might point at a real namespace.
    config = ClientConfig.load_client_connect_config(disable_file=True)
    config.setdefault("target_host", "localhost:7233")
    return await Client.connect(**config, plugins=plugins)
