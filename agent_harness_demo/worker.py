"""The worker that runs every Ziggy agent, their subagents, and their travel activities."""

from __future__ import annotations

import logging
import os

from google.genai import Client as GeminiClient
from temporalio.common import VersioningBehavior, WorkerDeploymentVersion
from temporalio.worker import Worker, WorkerDeploymentConfig

from temporal_agent_harness.ai_sdks.google_genai_plugin import GoogleGenAIPlugin
from temporal_agent_harness.plugin import AgentHarnessPlugin

from . import config
from .ziggy import activities
from .ziggy.conversational_subagent_workflow import ZiggyChatSubagentWorkflow
from .ziggy.conversational_workflow import ZiggyChatAgentWorkflow
from .ziggy.workflow import ZiggyDynamicAgentWorkflow


def deployment_config() -> WorkerDeploymentConfig | None:
    """Worker Versioning settings, when the catalog's Worker Controller supplies a version.

    Agents are PINNED: a conversation finishes on the build it started on, and new
    conversations start on the newest build. Workflow changes therefore ship as a new
    version, without patching.
    """
    build_id = os.environ.get("TEMPORAL_WORKER_BUILD_ID")
    if not build_id:
        return None
    return WorkerDeploymentConfig(
        version=WorkerDeploymentVersion(
            deployment_name=os.environ["TEMPORAL_DEPLOYMENT_NAME"], build_id=build_id
        ),
        use_worker_versioning=True,
        default_versioning_behavior=VersioningBehavior.PINNED,
    )


async def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set; the conversational agents need it.")
    storage = await config.payload_storage()
    # The harness plugin goes last so its payload converter, shared with the web process,
    # wraps the Gemini plugin's. It also registers the travel tools as activities, and runs
    # the writer that sends the agents' events to Redis.
    client = await config.connect(
        [
            GoogleGenAIPlugin(GeminiClient(api_key=api_key)),
            AgentHarnessPlugin(
                tools=activities.ALL_TOOLS,
                large_payload_offload=storage,
                event_stream=config.EVENT_STREAM,
            ),
        ]
    )
    worker = Worker(
        client,
        task_queue=config.TASK_QUEUE,
        workflows=[ZiggyChatAgentWorkflow, ZiggyChatSubagentWorkflow, ZiggyDynamicAgentWorkflow],
        deployment_config=deployment_config(),
    )
    logging.info("Polling %s in namespace %s", config.TASK_QUEUE, client.namespace)
    await worker.run()
