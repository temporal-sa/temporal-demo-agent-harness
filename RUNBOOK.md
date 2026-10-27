# Runbook: Agent Harness travel agent (Ziggy)

This runbook is for presenting the demo. The [README](README.md) explains what it is and how it's built.

## What it shows

Ziggy is a travel agent that books flights, seats, and hotels for a traveler. The model writes a short Python script for each step, every search and booking in that script is a Temporal Activity, and nothing that touches the outside world runs until a person approves it. Each conversation is one Workflow, so a worker crash in the middle of a booking costs nothing: the next worker carries on from the same step.

The demo makes three problems visible:

- **An agent that books things must wait for a person, for as long as the person takes.** Ziggy stops at every script, search, and booking, and at every choice between options. The wait is part of the Workflow, so it survives a closed tab or a restarted worker. Beats 2 and 3 show it.
- **A crash mid-booking must not lose the trip.** Kill the worker while three flights and two hotels are booking. The page stays up, the trip board says the bookings are delayed, and when a worker returns the same bookings finish, with no approval asked twice. Beat 4 shows it.
- **Code the model wrote has to run somewhere safe, and every action it takes has to stay visible.** The script runs in a sandbox whose only exits are the travel tools, and each call shows up as its own approval, its own Activity, and its own row on the departures board. Beat 2 shows it, and beat 5 shows the history.

## Before you start

- **On tmprl-demo.cloud,** open the Agent Harness catalog entry and press **Create crashable environment**, then **Open environment** once it shows **Running**. The app sits behind the catalog's sign-in. The environment gets its own Task Queue and worker, and the catalog supplies the Gemini key and the Temporal credentials.
- **Locally,** install [uv](https://docs.astral.sh/uv/), Node 22 or later, and the [Temporal CLI](https://docs.temporal.io/cli). The conversational agent needs a Gemini API key. Without one, you can still play the scripted trip in [Start it](#start-it); set `GEMINI_API_KEY` to any value so the worker starts.
- The demo never reads your Temporal CLI profile. It connects with `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE` and `TEMPORAL_API_KEY` only, and defaults to `localhost:7233` and `default`.

## Start it

In three terminals, from the repository root:

1. `temporal server start-dev`
2. `(cd ui && npm ci && npm run build)`, then `export TEMPORAL_ADDRESS=localhost:7233 GEMINI_API_KEY=...` and `uv run python -m agent_harness_demo worker`
3. `uv run python -m agent_harness_demo web` (with the same exports)

Open http://localhost:8000. A healthy start shows the **Route map** reading "Ready for departure", an empty **Departures** board that says "Tell Ziggy where you're going", and an empty **Conversation** panel with a suggested prompt. The worker terminal logs `Polling agent-harness in namespace default`. `GET /api/health` returns `{"ok":true,"task_queue":"agent-harness"}`. The Temporal UI is at http://localhost:8233.

Without the UI build, `/` redirects to the harness console. Rebuild the UI after pulling changes to `ui/`.

### Play a scripted trip without a model

To rehearse, or to present without a Gemini key, start the worker and web as above, then run:

```bash
uv run python -m scripts.preview_trip                 # asks before each search and booking
uv run python -m scripts.preview_trip --no-approvals  # runs straight through
```

It prints a link to open. The script plans SFO to New York to London and home: five searches at once, a choice of itinerary and fare, a hotel in each city, then three flights, two hotels, and three seats. The same Workflow, Activities, approval cards, choice cards, and trip board run; only Ziggy's chat replies are missing, and the message box doesn't apply.

## The walkthrough

Each beat takes a minute or two, longer when the model is slow. The model call shows a **thinking** badge with a timer, and after 30 seconds the chat explains that the Workflow is waiting on Gemini.

### 1. Start a trip and ask for one

1. Open the app. It starts a new trip or resumes your most recent one; **New trip** in the header starts a fresh one.
2. Type in the message box and press **Send** (or `Enter`): *"Book me a flight from SFO to JFK on November 3 and a hotel for three nights. Traveler is Ada Lovelace."*
3. Your message appears in **Conversation**, whose header reads "Each message is a Workflow Update". A **thinking** badge shows the model call running.
4. Say: "This conversation is a Temporal Workflow. My message just went in as an Update, and the model call is an Activity. If anything fails from here on, the conversation is already saved."

### 2. Approve the script, then the searches

1. A **Run a travel script** card appears with the Python Ziggy wrote. Read a line or two of it aloud, then press **Approve**.
2. The script asks for its searches all at once. They arrive as one card per tool, such as **Search flights × 2**, with **Approve all**, **Always allow**, and **Decline all**, plus a ✓ and ✕ for each call. The departures board shows those legs as **CLEARANCE**.
3. Press **Approve all**. The rows change to **SEARCHING** while the Activities run.
4. Say: "The model wrote code, and the code runs in a sandbox whose only way out is these travel tools. Every call it makes waits for me. The Workflow is holding that wait, not a thread on a server, so I could come back tomorrow."

**Always allow** approves the whole group and stops asking about that tool for the rest of the session. Use it on searches when you want to move faster, and keep bookings on manual approval so beat 4 has something to crash.

### 3. Pick an option, and approve the bookings

1. Ziggy shows its options as cards under **your choice**, with a button for each fare's total. Click a fare to pick that option and fare. For hotels, click **Book stay** on one. **None of these** sends a comment instead.
2. The chat comes back, and booking approvals appear: a **Book flight** card and a **Book hotel** card, or grouped cards if the script books several at once.
3. Say: "That question was a tool call too. The script stopped and waited for my click, durably, and got back a typed answer instead of guessing from free text."

### 4. Crash the worker in the middle of the bookings

1. Approve the bookings. The departures board shows **BOOKING...** for a few seconds per booking.
2. While they're booking, crash the worker:
   - **On tmprl-demo.cloud:** press **Crash workers** on the catalog's environment card. It force-deletes the worker pods; the web pod stays up, and a replacement worker starts.
   - **Locally:** run `pkill -9 -f "agent_harness_demo worker"` in another terminal, then start the worker again with `uv run python -m agent_harness_demo worker`.
3. After 10 to 15 seconds, the page shows a yellow **reconnecting** card: "Ziggy's worker isn't answering right now…". The departures board shows the interrupted rows as **DELAYED**, and the route map caption reads "Delayed · no worker answering".
4. Once a worker is running, the bookings finish and land as **CONFIRMED** with a confirmation code in **Conf**. Ziggy asks nothing again; the approvals you gave before the crash still count.
5. Say: "The worker died halfway through five bookings. Temporal noticed the bookings never reported back, and the new worker ran them again from the same point in the script. The conversation, the approvals, and the trip board were never on the worker."

A booking that was running when the worker died is retried when its 30-second start-to-close timeout runs out and a worker is polling, so the recovery can take up to about half a minute after the crash.

### 5. Show the proof

1. Click **Temporal UI ↗** in the header. It opens this conversation's Workflow.
2. In the event history, point out:
   - `send_agent_message` Updates for each message, `tool_approval` Updates for each approval, and `provide_callback_result` Updates for each choice.
   - One Activity per search, booking, and seat (`search_flights`, `book_flight`, `select_seat`, `book_hotel`, `get_seat_map`). Open a booking that was interrupted in beat 4: its **ActivityTaskStarted** event shows attempt 2, and the last failure is `activity StartToClose timeout`.
   - What isn't there: the reply text, tool events, and trip board changes the page streamed. Those went through Redis, so the history holds only the decisions and the work.
3. Or click **Harness console** for the same session as the harness sees it: the state flow, the raw events, the **Agent state** pane with the trip board, and a replay scrubber. **← Demo view** in its top bar comes back.
4. Say: "Every decision is in the history: what the model asked for, who approved it, and which attempt actually booked it."

### Optional: change settings mid-turn

Below the chat, **Approvals** switches the approval policy: **Ask for everything**, **Trust scripts** (scripts and the trip board run, searches and bookings still ask), or **Never ask**. **Model** switches between the two Gemini models. Both apply right away, even while a turn is running; the chat shows the change with an **applied** badge. Switching to a looser policy also releases calls already waiting for approval if the new policy allows them.

## Show it in code

All links point at commit [`eda32ba`](https://github.com/temporal-sa/temporal-demo-agent-harness/commit/eda32ba59215508d8c97507683e1551d87d92363). Open a file locally with `code -g <path>:<line>`.

The agent is built on the [Temporal Agent Harness](https://github.com/temporal-community/temporal-agent-harness) 0.7.0 with its Redis event stream, pinned in `pyproject.toml`. The harness provides the turn loop, the approval gate, Code Mode, and the event stream; this repo supplies the tools, the prompt, and the policy.

### Gate every outside call on a person

**When to use it:** after beat 2, or when someone asks how the agent is stopped from booking on its own.

**Where it is:** [`agent_harness_demo/ziggy/conversational_workflow.py` lines 181–199](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/conversational_workflow.py#L181-L199) (`code -g agent_harness_demo/ziggy/conversational_workflow.py:181`)

```python
@agent.init
def __init__(self, config: AgentConfig, data: TravelerContext | None = None) -> None:
    self._instruction = system_instruction(SYSTEM_INSTRUCTION, data)
    self._runner = AgentWorkflowRunner(
        config,
        stream=WorkflowStream(),
        # Demo stance: require human approval for EVERY tool call that reaches the outside
        # world — both the `run_travel_code` tool and each travel host call the script makes
        # (search/book flights & hotels), since every call is dispatched through run_tool and
        # gated. The trip-board tools are allowed by name, and only those: ...
        approval_policy_default=ToolApprovalPolicy.allow_tools(
            [*trip_board.BOARD_TOOL_NAMES, *choices.CHOICE_TOOL_NAMES]
        ),
    )
```

**What you need to understand:**

- The policy allow-lists the trip-board tools and the two choice tools by name. Everything else, including the script itself, waits for a person.
- The wait is a Workflow `wait_condition` inside the harness. An approval arrives as a `tool_approval` Update, so the decision and who made it are in the Workflow history. No Activity or timer runs while Ziggy waits.
- The harness keeps `tool_approval` separate from the message Update on purpose: a parent agent that drives this one can send it messages but can't approve its tool calls.
- **Always allow** sends the approval with `remember`, which adds that tool to the session's allow-list and releases the other waiting calls of it.
- The policy is live state. `set_approval_policy` (the **Approvals** menu) swaps it mid-turn; see [lines 246–259](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/conversational_workflow.py#L246-L259).
- A customer would pick their own line: approve bookings only, or allow searches by name. The harness also has an auto mode where an evaluator decides first and escalates to a person; this demo doesn't use it.

**Docs:** [Message passing: Updates](https://docs.temporal.io/encyclopedia/workflow-message-passing#sending-updates), [Temporal Agent Harness](https://github.com/temporal-community/temporal-agent-harness)

### Run the model's script in a sandbox whose only exits are the tools

**When to use it:** during beat 2, when the script card appears, or when someone asks what stops model-written code from doing anything it likes.

**Where it is:** [`agent_harness_demo/ziggy/conversational_workflow.py` lines 204–216](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/conversational_workflow.py#L204-L216) (`code -g agent_harness_demo/ziggy/conversational_workflow.py:204`)

```python
# The single model-facing tool: Code Mode over the travel tools. The model writes a
# Python script that calls the travel operations as async host functions; each host call
# runs as a durable, approval-gated activity via run_tool.
self._code_tool = agent.code_mode_tool(
    # The travel tools plus the board tools, in one sandbox: a script can book a
    # flight and record it on the board without a round trip through the model, so
    # the board cannot drift from what was actually booked.
    [*activities.ALL_TOOLS, *trip_board.BOARD_TOOLS, *choices.CHOICE_TOOLS],
    name="run_travel_code",
    # Hidden from the model and from the generated stubs: the script names the
    # trip, never the state it lives in.
    injections={"board": self.trip_board},
)
```

**What you need to understand:**

- The model sees one tool, `run_travel_code(script)`. The harness generates its description from the tools' signatures, and type-checks each script against them before it runs.
- The script runs in a [pydantic-monty](https://pypi.org/project/pydantic-monty/) sandbox: no filesystem, no network, no imports except `asyncio` and the host functions.
- The harness steps the script from Workflow code. When the script awaits host calls, each call goes through the same approval gate and runs as its own Activity, concurrently when the script gathers them. The script is deterministic given those results, so after a crash the new worker replays it to the same point.
- One script can make many calls with loops and `asyncio.gather`, so a five-search plan is one model call, not five.

**Docs:** [Temporal Agent Harness](https://github.com/temporal-community/temporal-agent-harness), [Activities](https://docs.temporal.io/activities)

### Each search and booking is an Activity with a timeout

**When to use it:** after beat 4, when someone asks why the bookings came back on their own.

**Where it is:** [`agent_harness_demo/ziggy/activities.py` lines 259–282](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/activities.py#L259-L282) (`code -g agent_harness_demo/ziggy/activities.py:259`), with the timeout at [lines 67–70](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/activities.py#L67-L70) and a non-retryable check at [lines 173–177](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/activities.py#L173-L177)

```python
_TRAVEL_ACTIVITY_TIMEOUT = timedelta(seconds=30)

# ...

def _require_flight(flight_id: str) -> None:
    if not FLIGHT_ID.match(flight_id):
        raise ApplicationError(
            f"No flight {flight_id}; use a flight_id from search_flights.", non_retryable=True
        )

# ...

@agent.activity_tool_defn(
    name="book_flight",
    activity_config=ActivityConfig(start_to_close_timeout=_TRAVEL_ACTIVITY_TIMEOUT),
)
async def book_flight_activity(request: FlightBookingRequest) -> FlightBookingResponse:
    """Book a flight at a fare level and return a confirmation code. Choose a seat afterward
    with `select_seat`."""
    activity.logger.info(
        "Booking %s (%s) for %s", request.flight_id, request.fare, request.passenger_name
    )
    _require_flight(request.flight_id)
    fare = next(f for f in _flight(request.flight_id).fares if f.level == request.fare)

    # Simulate the latency of confirming the booking with the airline.
    await asyncio.sleep(random.uniform(4.0, 6.0))

    return FlightBookingResponse(
        confirmation_code=_make_ref("AIR", request.flight_id, request.passenger_name, request.fare),
        # ...
    )
```

**What you need to understand:**

- `@agent.activity_tool_defn` makes one function both a tool the script can call and a Temporal Activity. The worker registers the Activity bodies through `AgentHarnessPlugin(tools=activities.ALL_TOOLS)` in `worker.py`.
- The 30-second start-to-close timeout is what detects the crash. The simulated calls take 2 to 6 seconds; when a worker dies mid-call, Temporal times the attempt out at 30 seconds and schedules attempt 2 on whichever worker polls next.
- There is no retry policy in the code, so Temporal's default applies: unlimited attempts, starting at 1 second and backing off to 100 seconds. A model-made mistake, such as a made-up flight ID, raises a non-retryable `ApplicationError` instead, which goes back to the script as an error rather than being retried forever.
- A retried booking runs the body again. This simulation returns the same confirmation code for the same flight, traveler, and fare; a real booking API needs an idempotency key, such as the Workflow ID plus the Activity ID, so a retry can't book twice.

**Docs:** [Activity timeouts](https://docs.temporal.io/encyclopedia/detecting-activity-failures#start-to-close-timeout), [Retry Policies](https://docs.temporal.io/encyclopedia/retry-policies#default-behavior), [Idempotency](https://docs.temporal.io/activities#idempotency)

### Ask the traveler, and wait as long as it takes

**When to use it:** during beat 3, when the option cards appear.

**Where it is:** [`agent_harness_demo/ziggy/choices.py` lines 61–65](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/choices.py#L61-L65) (`code -g agent_harness_demo/ziggy/choices.py:61`)

```python
@agent.callback_tool_defn(inherently_safe=True)
async def ask_traveler_to_choose(request: ChoiceRequest) -> Choice:
    """Show the traveler two or more trip options as cards, with each fare's total, and wait
    for them to pick an option and fare, or to say what they want instead."""
    ...
```

**What you need to understand:**

- A callback tool has no body. When the script calls it, the harness publishes the request on the session's event stream and waits in the Workflow until a client sends the answer as a `provide_callback_result` Update.
- The demo view draws the request as cards and sends the click back. The harness validates the answer against `Choice` before the script gets it, so the script books exactly the option and fare the traveler picked.
- No `timeout` is set, so the wait is unbounded, and like the approval gate it holds no worker resources. The session's 24-hour execution timeout is the only limit.
- A customer's version might be a mobile push, a Slack button, or a manager's sign-off. The tool definition stays the same; only the client that answers changes.

### The trip board is Workflow state the page watches

**When to use it:** while bookings land on the departures board, or when someone asks where the board's data comes from.

**Where it is:** [`agent_harness_demo/ziggy/conversational_workflow.py` lines 177–179](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/conversational_workflow.py#L177-L179) and [`agent_harness_demo/ziggy/trip_board.py` lines 374–383](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/trip_board.py#L374-L383) (`code -g agent_harness_demo/ziggy/trip_board.py:374`)

```python
@agent.defn(name="ZiggyChatAgent")
class ZiggyChatAgentWorkflow:
    trip_board = agent.state(trip_board.TripBoard)
```

```python
# The booking and the tasks it closes land in ONE mutate(), so a consumer of the state
# stream never observes a moment where they disagree.
with board.mutate() as draft:
    trip = draft.trips[index]
    if request.kind == "flight":
        trip.flights.append(booking)
    else:
        trip.hotels.append(booking)
    for position in matched:
        trip.remaining[position].done = True
```

**What you need to understand:**

- The board lives in the Workflow. Its tools are plain `@agent.tool_defn` functions that run inline, not Activities, because writing the agent's own notes doesn't touch the outside world.
- Each `mutate()` block publishes a JSON Patch on the session's event stream, and the demo view applies the patches to draw the board. The console's **Agent state** pane shows the same patches.
- Because the board is Workflow state, it survives the crash in beat 4 with the rest of the conversation.
- The script records each booking in the same script that made it, with the confirmation code the booking returned, so the board can't show something that wasn't booked.

### Model calls are Activities too

**When to use it:** when someone asks what happens if Gemini is slow or fails.

**Where it is:** [`agent_harness_demo/ziggy/conversational_workflow.py` lines 217–224](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/conversational_workflow.py#L217-L224) (`code -g agent_harness_demo/ziggy/conversational_workflow.py:217`)

```python
# The Temporal-aware AsyncClient from the Gemini plugin; the runner is wired in so reply
# text streams to the workflow stream as it is generated.
self._gemini = google_genai_client(
    activity_config=ActivityConfig(
        start_to_close_timeout=timedelta(minutes=3),
    ),
    runner=self._runner,
)
```

**What you need to understand:**

- The harness's Gemini plugin gives the Workflow a Gemini client whose API calls run as Activities. The Workflow code calls `gemini.interactions.create(...)` as usual; credentials stay on the worker.
- The 3-minute timeout allows for a slow first token. The reply streams to the page while the Activity runs.
- A timed-out call, a rate limit (429), or a server error is retried like any other Activity. Other client errors, such as a rejected API key, fail without retrying, because the same request would fail forever. A completed call is in history, so a crash after it never pays for the same call twice.
- The Workflow keeps the whole conversation and sends it on every call, so a new worker has everything it needs.

### Pin each conversation to the build it started on

**When to use it:** when someone asks how you change the agent while conversations are open.

**Where it is:** [`agent_harness_demo/worker.py` lines 22–38](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/worker.py#L22-L38) (`code -g agent_harness_demo/worker.py:22`)

```python
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
```

**What you need to understand:**

- On tmprl-demo.cloud, the catalog's Worker Controller sets `TEMPORAL_DEPLOYMENT_NAME` and `TEMPORAL_WORKER_BUILD_ID`, which turns on Worker Versioning. Locally neither is set, and the worker runs unversioned.
- `PINNED` keeps every Workflow on the Worker Deployment Version it started on. A conversation that is waiting on an approval for a day finishes on the code that started it, and new conversations start on the newest version.
- That is why the agent code has no `patched()` branches: changes ship as a new version instead.

**Docs:** [Worker Versioning](https://docs.temporal.io/worker-versioning)

### One Workflow per conversation, closed after a day

**When to use it:** when someone asks what a session is, or what happens to abandoned ones.

**Where it is:** [`agent_harness_demo/web.py` lines 276–283](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/web.py#L276-L283) (`code -g agent_harness_demo/web.py:276`), with the timeout from [`agent_harness_demo/config.py` lines 21–23](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/config.py#L21-L23)

```python
try:
    handle = await temporal().start_workflow(
        req.agent_workflow_type,
        args=[AgentConfig()] if data is None else [AgentConfig(), data],
        id=prefix + suffix,
        task_queue=config.TASK_QUEUE,
        execution_timeout=config.SESSION_TIMEOUT,
    )
```

```python
# Agents wait for their next message indefinitely, so an abandoned session is closed by
# Temporal when this runs out. Subagents close with their parent.
SESSION_TIMEOUT = timedelta(hours=float(os.environ.get("SESSION_TIMEOUT_HOURS", "24")))
```

**What you need to understand:**

- **New trip** starts one agent Workflow. Its ID is `<task queue>.<owner hash>.<session>`, so each signed-in person lists and opens only their own trips.
- The agent waits for its next message indefinitely, so the execution timeout (24 hours by default, `SESSION_TIMEOUT_HOURS`) is what closes an abandoned session.
- A production agent might instead run for weeks and use Continue-As-New to keep its history short; this demo's sessions are short enough not to need it.

### What's demo-only

When someone asks what they'd change for their own system, these are the parts to leave out:

- **The travel tools are simulated.** [`agent_harness_demo/ziggy/activities.py` lines 1–7](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/ziggy/activities.py#L1-L7): each Activity sleeps and returns data derived from its inputs. Replace the bodies with real API calls, with an idempotency key on each booking.
- **Per-person scoping lives in the web API.** [`agent_harness_demo/web.py` lines 109–142](https://github.com/temporal-sa/temporal-demo-agent-harness/blob/eda32ba59215508d8c97507683e1551d87d92363/agent_harness_demo/web.py#L109-L142) hashes the catalog's sign-in header into the Workflow ID prefix and checks it on every route. A customer would use their own auth.
- **The scripted trip uses a different agent.** `scripts/preview_trip.py` starts `ZiggyDynamicAgent`, which has no model and runs the script it's sent. It turns approvals on for the preview; on its own it skips them.

## Reset and tear down

- **Between runs:** press **New trip**. The old trip stays open in Temporal until its 24-hour execution timeout, but the page moves to the new one. To end a session sooner, terminate its Workflow from the Temporal UI.
- **To stop locally:** stop the web, the worker, Redis, and the dev server with `Ctrl-C`. `temporal server start-dev` and Redis keep their data in memory, so stopping them discards every session.
- **On tmprl-demo.cloud:** press **Delete** on the environment card when you're done, or let it expire; **Extend +1h** gives you more time.

## When something goes wrong

| What you see | Likely cause | Fix |
|---|---|---|
| `/` opens the harness console, not the demo view | The UI wasn't built | Run `(cd ui && npm ci && npm run build)` and restart the web process |
| The web or worker logs a Redis connection error, or the worker logs `Dropping N events` | Redis isn't running, or the two processes have different `REDIS_URL`s | Start `redis-server`. The page streams nothing until it's back, but turns still finish; reload once it is |
| The worker exits with "GEMINI_API_KEY is not set" | No key in the worker's environment | Export `GEMINI_API_KEY`; for the scripted trip any value works |
| A message stays "Sending…" and the yellow **reconnecting** card shows | No worker is polling the Task Queue. A message is an Update, and a worker has to accept it | Start the worker. On tmprl-demo.cloud, press **Scale up workers** if the card shows "Workers scaled to zero" |
| **thinking** runs for minutes | Gemini is slow to send its first token | Wait; the chat says so after 30 seconds. Past the 3-minute start-to-close timeout the Activity is retried |
| A booking stays **DELAYED** after the worker is back | The interrupted attempt hasn't hit its 30-second start-to-close timeout yet | Wait up to half a minute |
| Ziggy asks to run a second script for the same step | The first script failed its type check or raised. The error goes back to the model as the tool's result, and Ziggy writes a corrected script | Approve the new script; this is normal |
| The worker fails to import `google.genai._interactions` | `google-genai` 2.9.0 or later is installed | Run `uv sync`; `pyproject.toml` caps it below 2.9 |

## Keeping this runbook current

The code links point at a fixed commit. When a linked file changes, update its link, line numbers, and snippet together. Before an event, list the linked files that have changed:

```sh
grep -oE 'blob/[0-9a-f]{40}/[^#)]+' RUNBOOK.md | sort -u | while IFS=/ read -r _ sha file; do
  git diff --quiet "$sha" HEAD -- "$file" || echo "changed since ${sha:0:7}: $file"
done
```
