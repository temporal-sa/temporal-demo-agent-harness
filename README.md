# Agent Harness: Ziggy the travel agent

Ziggy is a conversational travel agent built on the [Temporal Agent Harness](https://github.com/temporal-community/temporal-agent-harness). You ask for a trip, and the model writes a short Python script that runs in a [pydantic-monty](https://pypi.org/project/pydantic-monty/) sandbox. Each flight or hotel search, seat map, and booking in that script is a durable Temporal Activity, and each tool call waits for your approval. Flights come in economy, premium, and business fares. When Ziggy has options to offer, it shows them as cards in your browser and waits for you to pick one: that question is a harness callback tool, answered by the page rather than a worker, and the Workflow holds it durably until you choose. After booking, Ziggy offers seats from the flight's seat map, with each seat's perks and drawbacks. The trip board shows what's booked and what's left, and it updates as the bookings land.

Because the conversation is a Workflow, you can kill the worker in the middle of a booking. When a worker comes back, the agent carries on from the same step, with the same approvals and the same trip board.

This repository is the tmprl-demo.cloud catalog version of the harness's [Monty example](https://github.com/temporal-community/temporal-agent-harness/tree/0.6.0/examples/monty). It replaces the adapter in the registry repo (`deployments/monty/`), which downloaded a pinned upstream tarball and patched it during the image build.

The upstream example names its agent Monty, after the sandbox. Here the agent is Ziggy, Temporal's mascot, so "Monty" only ever means the pydantic-monty sandbox that runs the scripts.

## The demo

The app has two views of the same sessions, and each links to the other with the session kept:

- **Demo view** (`/`): the trip board, the conversation, and approval cards, in the Temporal demo theme. Visitors land here.
- **Harness console** (`/console/`): the harness's own UI, unchanged, with the state flow, raw events, and a replay scrubber. Open it from **Harness console** in the header; **← Demo view** in its top bar comes back.

1. Open the app. It starts a trip, or resumes your most recent one.
2. Ask: *"Book me a flight from SFO to JFK on November 3 and a hotel for three nights. Traveler is Ada Lovelace."*
3. Pick an itinerary and fare from the option cards, then approve each card as it appears: the script Ziggy wrote, then each search and booking that script makes. Bookings land on the departures board as they happen.
4. In a crashable workspace, choose **Crash Workers** while a booking is in progress. The page stays up and says the worker isn't answering. When the replacement worker starts, the turn finishes where it stopped.
5. Open **Harness console** to show the same turn as events and state flow, or **Temporal UI** to show the Workflow history.

The console can also start **Ziggy (Conversational, Subagent)**, which hands each script to a separate script-runner agent running as a child Workflow. The demo view shows that variant's trip board from the subagent.

## Run it locally

To present the demo, follow [RUNBOOK.md](RUNBOOK.md): the walkthrough beat by beat, and where in the code each part happens.

You need [uv](https://docs.astral.sh/uv/), Node 22 or later, the [Temporal CLI](https://docs.temporal.io/cli), and a Gemini API key.

```bash
temporal server start-dev
(cd ui && npm ci && npm run build)             # builds the demo view into agent_harness_demo/ui_dist
export TEMPORAL_ADDRESS=localhost:7233 GEMINI_API_KEY=...
uv run python -m agent_harness_demo worker     # terminal 1
uv run python -m agent_harness_demo web        # terminal 2, then open http://localhost:8000
```

To see the demo view without a Gemini key, play a scripted trip through a script-only Ziggy agent. The Workflow, Activities, approvals, trip board, map, and departures board all run as usual; only the model's replies are missing:

```bash
uv run python -m scripts.preview_trip                 # asks before each search and booking
uv run python -m scripts.preview_trip --no-approvals  # runs straight through
```

It prints a link to open. Stop the worker while a booking runs to see the delayed state, then start it again.

Without the UI build, `/` redirects to the console. To work on the demo view, run `npm run dev` in `ui/` and open http://localhost:5173; it proxies the API to the web process on :8000.

Or run both processes in containers against the same dev server:

```bash
GEMINI_API_KEY=... docker compose up --build
```

Run the tests with `uv run pytest`. They start their own dev server and need no API key.

## How it's put together

```
agent_harness_demo/
  ziggy/        the agents, their tools, and the trip board (copied from the harness's Monty example)
  web.py        the browser API and both views, scoped to the signed-in person
  worker.py     one worker for all three agent Workflows and their Activities
  config.py     environment settings shared by both processes
ui/                         the demo view: Svelte 5 on @temporalio/agent-harness-svelte
  src/generated/            TypeScript types for ZiggyChatAgent, generated from the Python class
deploy/agent-harness.yaml   draft DemoProject for the registry
```

The harness comes from PyPI, pinned to `temporal-agent-harness==0.6.0`. The console is served unchanged from the installed package. The demo view uses the harness's npm packages, `@temporalio/agent-harness-svelte` and `-client` 0.1.0, which follow a session's event stream and expose its messages, pending approvals, and the `trip_board` state. It calls the same routes as the console, so it gets the same per-person scoping. The Dockerfile builds it in a Node stage; the runtime image has no Node.

When the agent's handlers or `TripBoard` change, regenerate the types. The generator ships in the harness repo, not on npm:

```bash
uv run temporal-agent-harness schema agent_harness_demo.ziggy.conversational_workflow:ZiggyChatAgentWorkflow > /tmp/ziggy.json
# in a checkout of temporal-agent-harness at the pinned tag:
(cd packages/codegen && npm ci && npm run build)
node packages/codegen/dist/src/cli.js /tmp/ziggy.json -o <this repo>/ui/src/generated/ZiggyChatAgent.ts
```

Changes from the upstream example:

- **No session-manager Workflow.** The harness's web app keeps one long-running session manager per namespace and lists every agent in the namespace. Here, the API starts each agent Workflow directly and lists sessions with a Visibility query on the caller's ID prefix.
- **Per-person isolation.** Session IDs are `<task queue>.<owner>.<session>`, where `owner` is a hash of `X-Temporal-Auth-Subject`. Every route that names a session returns 404 unless the caller owns it, or owns the agent that started it as a subagent.
- **Task queue from one variable.** The web and worker processes both read `TEMPORAL_TASK_QUEUE`. Subagents run on their parent's queue (`workflow.info().task_queue`) rather than a hard-coded one.
- **Bounded sessions.** Agents wait for messages indefinitely, so every session starts with a Workflow execution timeout (`SESSION_TIMEOUT_HOURS`, 24 by default). Subagents close with their parent.

## Configuration

| Variable | Used by | Default | Purpose |
|---|---|---|---|
| `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY`, `TEMPORAL_TLS*` | both | `localhost:7233`, `default` | Temporal connection. `temporal.toml` files are ignored. |
| `TEMPORAL_TASK_QUEUE` | both | `agent-harness` | Queue for every agent. The catalog sets it per workspace. |
| `GEMINI_API_KEY` | worker | required | Model calls. |
| `PAYLOAD_BUCKET` | both | unset | S3 bucket for payloads over 1.5 MB. |
| `PAYLOAD_DIR` | both | harness default | Local directory for those payloads when no bucket is set. Web and worker must share it. |
| `TRUST_AUTH_HEADERS` | web | `false` | Read the user from `X-Temporal-Auth-Subject`. Set it only behind the catalog ingress. |
| `DEV_USER` | web | `local-dev` | The user when auth headers aren't trusted. |
| `SESSION_TIMEOUT_HOURS` | web | `24` | Execution timeout for each session. |
| `TEMPORAL_UI_URL` | web | Cloud or `localhost:8233`, from the address | Namespace URL in the Temporal UI, for the demo view's **Temporal UI** link. |
| `TEMPORAL_DEPLOYMENT_NAME`, `TEMPORAL_WORKER_BUILD_ID` | worker | unset | Set by the catalog's Worker Controller to turn on Worker Versioning. |

## Catalog decisions

1. **Session boundary:** the signed-in person, read from `X-Temporal-Auth-Subject`, which the catalog's forward-auth sets and the ingress strips from client requests. Each crashable-workspace share-link guest gets their own `share:<id>` subject.
2. **Scoping:** Workflow IDs start with `<task queue>.<sha256(subject)[:16]>.`. Listing, status, streams, messages, approvals and close all check that prefix. A subagent is allowed when its parent has the prefix.
3. **Task queue:** `TEMPORAL_TASK_QUEUE`, with base `agent-harness`. The API starts agents on it, and subagents inherit it from their parent.
4. **Sharing a namespace across workspaces:** the queue is part of every Workflow ID, and listing also filters on `TaskQueue`. Payload objects in S3 are keyed by content hash.
5. **Builds and components:** one image with two components: `web` (`args: [web]`, `temporalAccess`) and `worker` (`args: [worker]`, versioned, PINNED).
6. **Routes:** one ingress host, served by `web` on port 8000: the demo view at `/`, the console at `/console/`, and the API at `/api/` and `/console/api/`. Both views call relative `api/...` paths.
7. **Temporal credentials:** injected by the platform as `TEMPORAL_*` environment variables.
8. **Secrets and external state:** the shared `gemini` secret (worker only). Payloads use the S3 bucket and IAM role that Monty uses today. See the known gaps below.
9. **Smoke check:** `GET /api/health`. It needs no sign-in and touches no state.
10. **Known gaps:** listed below.

## Known gaps

- **IAM trust for the payload role.** The payload bucket's IAM role, shared with today's Monty project, trusts Monty's service accounts only. The new `agent-harness` project and its crashable namespaces need to be added before cutover, or the bucket and role need replacing with ones named for this project.
- **`google-genai` cap.** The harness's Gemini plugin imports `google.genai._interactions`, which `google-genai` 2.9.0 removed. The harness declares only `>=2.0.0`, so `pyproject.toml` caps it at `<2.9`. This is worth reporting upstream.
- **Messages wait for a worker.** Sending a message is a Workflow Update, which a worker must accept. While no worker runs, the send stays open and the demo view says so; it goes through when a worker returns, unless the browser gives up on the request first.
- **Private harness helpers.** `web.py` imports a few private helpers from `temporal_agent_harness.web.app`, so that the UI gets byte-identical responses. That's safe only while the harness version is pinned. Review them when upgrading.
- **Upgrade path.** Bump the harness pin, re-copy `examples/monty` from the matching tag, and keep the two local changes: no hard-coded queue, and subagents inherit their parent's queue. Workflow changes ship as a new Worker Deployment Version without patching, because agents are PINNED.
