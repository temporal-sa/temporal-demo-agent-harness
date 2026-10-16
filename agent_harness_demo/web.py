"""The browser API and both UIs, scoped so each signed-in person sees only their own agents.

Two views share one API and the same sessions:

* `/` is the demo view (`ui/`), built on the harness's npm client in the Temporal demo theme.
* `/console/` is the harness's own packaged UI, unchanged apart from a link back to `/`.

The API routes match the harness's own web app (`temporal_agent_harness.web.app`), with two
changes for a shared catalog deployment:

* Sessions are agent workflows started directly, with IDs of the form
  `<task queue>.<owner>.<session>`, and listed with a Visibility query on that prefix. The
  harness's singleton session-manager workflow is not used, so one person's list never
  includes another's and nothing runs forever on the side.
* Every route that names a session checks that the caller owns it (or owns its parent, for
  a subagent) before it reads, streams, or changes anything.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import secrets
import time
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated, AsyncIterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from temporal_agent_harness.harness.agent_client import (
    AgentClient,
    AgentStreamOutput,
    AgentTurnError,
    AgentTurnTimeout,
    CallbackResultError,
    JoinedTurnError,
    MidTurnRejectedError,
    ToolApprovalError,
)
from temporal_agent_harness.harness.agent_protocol import AgentConfig, AgentStatus
from temporal_agent_harness.plugin import AgentHarnessPlugin
from temporal_agent_harness.ui import packaged_ui_dist
from temporal_agent_harness.web.agent_starts import (
    InvalidStartData,
    resolve_agent_starts,
    validated_start_data,
)
from temporal_agent_harness.web.registry import load_agent_registry
from temporal_agent_harness.web.session_manager import AgentRegistry, Session
from temporal_agent_harness.web.task_queue_status import describe_task_queue_workers

# Request bodies, SSE framing, and session previews are reused from the harness's own app so
# the packaged UI sees identical responses. They are private names, which is safe only
# because pyproject.toml pins the harness to an exact version.
from temporal_agent_harness.web.app import (
    STREAM_ERROR_SSE_EVENT,
    CallbackResultRequestBody,
    ChatRequestBody,
    CreateSessionRequestBody,
    ToolApprovalRequestBody,
    _session_with_execution_state,
    _sse,
    _sse_headers,
    _update_id,
    _workflow_execution_state,
    _yield_item,
)

from . import config

# Behind the catalog ingress, the SSO gate sets this header and clients cannot. Anywhere
# else it is just a header anyone can send, so it is ignored unless the deployment says so.
TRUST_AUTH_HEADERS = os.environ.get("TRUST_AUTH_HEADERS", "").lower() == "true"
AUTH_SUBJECT_HEADER = "X-Temporal-Auth-Subject"
DEV_USER = os.environ.get("DEV_USER", "local-dev")

NO_STORE = {"Cache-Control": "no-store"}
SESSION_LIST_LIMIT = 50
# What may follow the owner prefix in a session ID the browser chooses.
SESSION_SUFFIX = re.compile(r"[A-Za-z0-9_-]{1,64}")

# A model call can stream nothing for minutes before its first word. Load balancers close a
# connection that stays idle (AWS's default is 60 seconds), so a quiet stream gets an SSE
# comment this often; the browser's parser skips comments.
KEEPALIVE_SECONDS = 15
KEEPALIVE = b": keepalive\n\n"

DEMO_UI_DIST = Path(__file__).parent / "ui_dist"
# Added to the console's page so each view can open the same session in the other.
CONSOLE_BACK_LINK = """<a id="demo-view-link" href="../" style="position:fixed;right:150px;top:12px;z-index:9999;
padding:6px 10px;font:500 12px/1 'Noto Sans Mono',ui-monospace,monospace;color:#f8fafc;
background:#141414;border:1px solid #6169ed;text-decoration:none">&larr; Demo view</a>
<script>document.getElementById("demo-view-link").addEventListener("click", (event) => {
  const s = new URLSearchParams(location.search).get("s");
  event.currentTarget.href = "../" + (s ? "?s=" + encodeURIComponent(s) : ""); });</script>
"""


def owner_prefix(request: Request) -> str:
    """The workflow ID prefix for the caller's sessions on this deployment's task queue."""
    if TRUST_AUTH_HEADERS:
        subject = request.headers.get(AUTH_SUBJECT_HEADER)
        if not subject:
            raise HTTPException(status_code=401, detail="Sign-in required")
    else:
        subject = DEV_USER
    return prefix_for(subject)


def prefix_for(subject: str) -> str:
    # A hash keeps email addresses and SSO subjects out of workflow IDs.
    owner = hashlib.sha256(subject.encode()).hexdigest()[:16]
    return f"{config.TASK_QUEUE}.{owner}."


Owner = Annotated[str, Depends(owner_prefix)]


async def require_owned(temporal: Client, prefix: str, workflow_id: str) -> None:
    """Allow the caller's own sessions and the subagents those sessions started."""
    if workflow_id.startswith(prefix):
        return
    try:
        description = await temporal.get_workflow_handle(workflow_id).describe()
    except RPCError as err:
        if err.status != RPCStatusCode.NOT_FOUND:
            raise
    else:
        if (description.parent_id or "").startswith(prefix):
            return
    # 404 rather than 403, so IDs belonging to other people aren't confirmed to exist.
    raise HTTPException(status_code=404, detail="Session not found")


async def with_keepalive(
    stream: AsyncIterator[bytes], every: float = KEEPALIVE_SECONDS
) -> AsyncIterator[bytes]:
    """The stream's frames as they come, with a keepalive comment whenever it's quiet for `every`."""
    items = aiter(stream)
    pending = asyncio.ensure_future(anext(items))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=every)
            if not done:
                yield KEEPALIVE
                continue
            try:
                frame = pending.result()
            except StopAsyncIteration:
                return
            yield frame
            pending = asyncio.ensure_future(anext(items))
    finally:
        # Let the cancelled read finish before closing the stream it was reading.
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        if hasattr(items, "aclose"):
            await items.aclose()


def load_registry() -> AgentRegistry:
    registry = load_agent_registry(config.REGISTRY_PATH)
    for descriptor in registry.agents:
        descriptor.task_queue = config.TASK_QUEUE
    return registry


def create_app() -> FastAPI:
    registry = load_registry()
    agent_starts = resolve_agent_starts(registry)
    agent_types = [descriptor.workflow_type for descriptor in registry.agents]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = await config.payload_storage()
        app.state.temporal = await config.connect(
            [AgentHarnessPlugin(large_payload_offload=storage)]
        )
        yield

    app = FastAPI(lifespan=lifespan)
    api = APIRouter()

    def temporal() -> Client:
        return app.state.temporal

    async def owned_agent(prefix: str, session_id: str) -> AgentClient:
        await require_owned(temporal(), prefix, session_id)
        return AgentClient(temporal=temporal(), workflow_id=session_id)

    @api.get("/health")
    async def health():
        # The server only starts serving after it has connected to Temporal, so reaching this
        # proves that wiring without calling Temporal or touching session state.
        return {"ok": True, "task_queue": config.TASK_QUEUE}

    @api.get("/agents")
    async def list_agents():
        workers = await describe_task_queue_workers(temporal(), [config.TASK_QUEUE])
        agents = [
            {
                **asdict(descriptor),
                "init_data": (
                    agent_starts[descriptor.workflow_type].init_data_schema
                    if descriptor.workflow_type in agent_starts
                    else None
                ),
                "worker": asdict(workers.for_task_queue(descriptor.task_queue)),
            }
            for descriptor in registry.agents
        ]
        return JSONResponse({"agents": agents}, headers=NO_STORE)

    async def running_sessions(prefix: str) -> list[dict]:
        types = " OR ".join(f"WorkflowType='{t}'" for t in agent_types)
        query = (
            f"TaskQueue='{config.TASK_QUEUE}' AND WorkflowId STARTS_WITH '{prefix}' "
            f"AND ExecutionStatus='Running' AND ({types})"
        )
        sessions = [
            Session(
                workflow_id=execution.id,
                created_at=execution.start_time.timestamp(),
                label=registry.by_workflow_type(execution.workflow_type).label,
                agent_workflow_type=execution.workflow_type,
            )
            async for execution in temporal().list_workflows(query, limit=SESSION_LIST_LIMIT)
        ]
        return list(
            await asyncio.gather(
                *(_session_with_execution_state(temporal(), session) for session in sessions)
            )
        )

    @api.get("/view")
    async def view(prefix: Owner):
        """Everything the demo view needs on load, in one request."""
        return JSONResponse(
            {
                "session_prefix": prefix,
                "temporal_ui_url": config.temporal_ui_url(temporal().namespace),
                "sessions": await running_sessions(prefix),
            },
            headers=NO_STORE,
        )

    @api.get("/sessions")
    async def list_sessions(prefix: Owner):
        return await running_sessions(prefix)

    @api.post("/sessions")
    async def create_session(req: CreateSessionRequestBody, prefix: Owner):
        descriptor = registry.by_workflow_type(req.agent_workflow_type)
        if descriptor is None:
            raise HTTPException(status_code=404, detail="Unknown agent")
        data = validated_start_data(
            req.agent_workflow_type, agent_starts.get(req.agent_workflow_type), req.data
        )
        # The demo view names its session (prefix included) so it can open it before this
        # returns. Any other caller-chosen ID is placed inside the caller's own prefix.
        suffix = req.session_id or secrets.token_hex(6)
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix) :]
        if not SESSION_SUFFIX.fullmatch(suffix):
            raise HTTPException(status_code=422, detail="Invalid session ID")
        try:
            handle = await temporal().start_workflow(
                req.agent_workflow_type,
                args=[AgentConfig()] if data is None else [AgentConfig(), data],
                id=prefix + suffix,
                task_queue=config.TASK_QUEUE,
                execution_timeout=config.SESSION_TIMEOUT,
            )
        except WorkflowAlreadyStartedError:
            raise HTTPException(status_code=409, detail="Session ID already in use")
        session = Session(
            workflow_id=handle.id,
            created_at=time.time(),
            label=descriptor.label,
            agent_workflow_type=req.agent_workflow_type,
        )
        return await _session_with_execution_state(temporal(), session)

    @api.get("/workflow-status/{workflow_id}")
    async def workflow_status(workflow_id: str, prefix: Owner):
        await require_owned(temporal(), prefix, workflow_id)
        content = await _workflow_execution_state(temporal(), workflow_id)
        return JSONResponse(content, headers=NO_STORE)

    @api.get("/status/{session_id}")
    async def get_status(session_id: str, prefix: Owner):
        agent = await owned_agent(prefix, session_id)
        status = TypeAdapter(AgentStatus).dump_python(await agent.get_status(), mode="json")
        return JSONResponse(status, headers=NO_STORE)

    @api.post("/sessions/{session_id}/close")
    async def close_session(session_id: str, prefix: Owner):
        await require_owned(temporal(), prefix, session_id)
        await temporal().get_workflow_handle(session_id).signal("close")
        return JSONResponse({"ok": True}, headers=NO_STORE)

    @api.get("/agent-interface/{session_id}")
    async def agent_interface(session_id: str, prefix: Owner):
        agent = await owned_agent(prefix, session_id)
        functions = await agent.get_agent_interface()
        return JSONResponse([fn.model_dump(mode="json") for fn in functions])

    @api.get("/attach")
    async def attach(session_id: str, prefix: Owner, from_offset: int = 0):
        agent = await owned_agent(prefix, session_id)
        return StreamingResponse(
            with_keepalive(await agent.attach(on_item=_yield_item, from_offset=from_offset)),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    @api.post("/approve")
    async def approve_tool(req: ToolApprovalRequestBody, prefix: Owner):
        agent = await owned_agent(prefix, req.session_id)
        result = await agent.approve_tool(
            req.tool_id, approved=req.approved, reason=req.reason, remember=req.remember
        )
        return JSONResponse(asdict(result), headers=NO_STORE)

    @api.post("/callback-result")
    async def provide_callback_result(req: CallbackResultRequestBody, prefix: Owner):
        agent = await owned_agent(prefix, req.session_id)
        result = await agent.provide_callback_result(
            req.tool_id, result=req.result, error=req.error
        )
        return JSONResponse(asdict(result), headers=NO_STORE)

    @api.post("/messages")
    async def submit_message(req: ChatRequestBody, prefix: Owner):
        agent = await owned_agent(prefix, req.session_id)
        msg_type, payload = _message_parts(req)
        result = await agent.submit_message(msg_type, payload, update_id=_update_id(req))
        return JSONResponse(asdict(result), headers=NO_STORE)

    @api.post("/chat")
    async def chat(req: ChatRequestBody, prefix: Owner):
        agent = await owned_agent(prefix, req.session_id)

        def on_item(item: AgentStreamOutput, resume_offset: int) -> bytes:
            match item:
                case AgentTurnTimeout():
                    error = {"kind": "timeout", "message": str(item)}
                case AgentTurnError():
                    error = {"kind": "agent", "message": str(item)}
                case _:
                    return _yield_item(item, resume_offset)
            return _sse(STREAM_ERROR_SSE_EVENT, error, resume_offset)

        msg_type, payload = _message_parts(req)
        return StreamingResponse(
            with_keepalive(
                await agent.send_message(msg_type, payload, on_item=on_item, update_id=_update_id(req))
            ),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    # The console calls `api/...` relative to its own page, so it gets the same routes there.
    app.include_router(api, prefix="/api")
    app.include_router(api, prefix="/console/api")
    _add_error_handlers(app)
    _mount_uis(app)
    return app


def _mount_uis(app: FastAPI) -> None:
    """Static UIs go last, so their catch-all mounts can't shadow the API."""
    console = packaged_ui_dist()
    console_index = (console / "index.html").read_text().replace(
        "</body>", CONSOLE_BACK_LINK + "</body>"
    )

    @app.get("/console", include_in_schema=False)
    async def console_redirect(request: Request):
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"console/{query}")

    @app.get("/console/", include_in_schema=False)
    async def console_page():
        return HTMLResponse(console_index)

    app.mount("/console", StaticFiles(directory=console), name="console")
    if DEMO_UI_DIST.is_dir():
        app.mount("/", StaticFiles(directory=DEMO_UI_DIST, html=True), name="demo")
    else:

        @app.get("/", include_in_schema=False)
        async def demo_not_built():
            # Local runs without `npm run build` in ui/ still have the console.
            return RedirectResponse("console/")


def _message_parts(req: ChatRequestBody) -> tuple[str, dict]:
    if isinstance(req.message, str):
        return "ask", {"text": req.message}
    return req.message["type"], req.message.get("payload") or {}


def _add_error_handlers(app: FastAPI) -> None:
    """The same status codes and bodies the harness's app returns, which the UI relies on."""

    @app.exception_handler(JoinedTurnError)
    async def joined_turn(_, exc: JoinedTurnError):
        return JSONResponse(
            status_code=409,
            content={"error": "joined_turn", "message": str(exc), "reply": asdict(exc.reply)},
        )

    @app.exception_handler(InvalidStartData)
    async def invalid_start_data(_, exc: InvalidStartData):
        return JSONResponse(
            status_code=422,
            content={"error": "invalid_init_data", "message": str(exc), "errors": exc.errors},
        )

    @app.exception_handler(MidTurnRejectedError)
    async def mid_turn_rejected(_, exc: MidTurnRejectedError):
        return JSONResponse(
            status_code=409, content={"error": "mid_turn_rejected", "message": str(exc)}
        )

    @app.exception_handler(ToolApprovalError)
    async def tool_approval(_, exc: ToolApprovalError):
        return JSONResponse(
            status_code=409,
            content={"error": exc.error_type or "tool_approval_error", "message": str(exc)},
        )

    @app.exception_handler(CallbackResultError)
    async def callback_result(_, exc: CallbackResultError):
        return JSONResponse(
            status_code=409,
            content={"error": exc.error_type or "callback_result_error", "message": str(exc)},
        )
