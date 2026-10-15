"""A throwaway Temporal dev server for tests, using the installed `temporal` CLI if present."""

import shutil

from temporalio.testing import WorkflowEnvironment


async def start_workflow_environment(**kwargs) -> WorkflowEnvironment:
    # The SDK otherwise downloads a server binary, which fails on machines without access
    # to temporal.download.
    return await WorkflowEnvironment.start_local(
        dev_server_existing_path=shutil.which("temporal"), **kwargs
    )
