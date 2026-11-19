"""Runtime settings shared by the web and worker processes, read from the environment."""

from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from temporalio.client import Client, Plugin
from temporalio.converter import ExternalStorage
from temporalio.envconfig import ClientConfig

from temporal_agent_kit.utils.large_payload import local_payload_storage, s3_payload_storage

REGISTRY_PATH = Path(__file__).parent / "ziggy" / "agents.toml"

# The catalog injects a per-workspace queue (`agent-harness-<workspace>`) into every
# component through this variable; see `crashable.taskQueueEnv` in the DemoProject.
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "agent-harness")

# An agent nobody has sent a message for this long closes itself (Agent Kit's
# close_after_idle). A turn waiting on an approval or a choice is not idle, so it never closes
# one that way; 0 turns it off. Subagents close with their parent.
SESSION_IDLE_CLOSE = timedelta(minutes=float(os.environ.get("SESSION_IDLE_CLOSE_MINUTES", "30")))

# The backstop: a session still open after this, waiting on an approval nobody gives for
# example, is closed by Temporal.
SESSION_TIMEOUT = timedelta(hours=float(os.environ.get("SESSION_TIMEOUT_HOURS", "24")))


def temporal_ui_url(namespace: str) -> str:
    """Base URL for this namespace in the Temporal UI, for links from the demo view.

    The demo platform injects TEMPORAL_UI_URL as the UI's base (https://cloud.temporal.io,
    or a crashable workspace's dev server UI) and TEMPORAL_UI_NAMESPACE as the namespace.
    """
    if url := os.environ.get("TEMPORAL_UI_URL"):
        url = url.rstrip("/")
        if "/namespaces/" in url:
            return url  # already a namespace page
        return f"{url}/namespaces/{quote(os.environ.get('TEMPORAL_UI_NAMESPACE') or namespace, safe='')}"
    if os.environ.get("TEMPORAL_ADDRESS", "").endswith(".tmprl.cloud:7233"):
        return f"https://cloud.temporal.io/namespaces/{namespace}"
    return f"http://localhost:8233/namespaces/{namespace}"


async def payload_storage() -> ExternalStorage:
    """Where the kit offloads payloads above ~1.5 MB (sandbox snapshots, long histories).

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
