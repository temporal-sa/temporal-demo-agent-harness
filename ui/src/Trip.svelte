<script lang="ts">
  import { AgentSession } from "@temporalio/agent-kit-svelte";
  import { transport } from "./api.ts";
  import type { ZiggyChatAgent, TripBoard as Board } from "./generated/ZiggyChatAgent.ts";
  import ApprovalQueue from "./ApprovalQueue.svelte";
  import ChoiceCards from "./ChoiceCards.svelte";
  import { isChoiceTool } from "./choices.ts";
  import Conversation from "./Conversation.svelte";
  import { MODELS, type Model, type Policy } from "./format.ts";
  import Settings from "./Settings.svelte";
  import Departures from "./Departures.svelte";
  import { motion } from "./motion.svelte.ts";
  import RouteMap from "./RouteMap.svelte";
  import { departures } from "./travel.ts";

  let { sessionId, newTrip }: { sessionId: string; newTrip: () => void } = $props();

  const agent = new AgentSession<ZiggyChatAgent>({
    get sessionId() {
      return sessionId;
    },
  });

  // The board lives on whichever agent in the tree runs the scripts: the root for Ziggy
  // (Conversational), its script-runner subagent for the subagent variant.
  const board = $derived(
    agent.states.trip_board ??
      (Object.values(agent.agents).find((view) => view.states.trip_board)?.states.trip_board as
        | Board
        | undefined),
  );
  const messages = $derived([...agent.messages, ...agent.pending]);

  // The agent's settings are whatever its latest model and policy messages set. A change shows
  // as soon as it is sent and drops back if the agent refuses it.
  type Message = (typeof messages)[number];
  type Sent<H extends Message["handler"]> = Extract<Message, { handler: H }>;
  const latest = <H extends Message["handler"]>(handler: H) =>
    messages.findLast((m): m is Sent<H> => m.handler === handler && m.status !== "error");

  const model: Model = $derived(latest("set_model")?.input.model ?? MODELS[0]);
  const policy: Policy | null = $derived(latest("set_approval_policy")?.input.new_policy ?? null);

  // The page can't see a worker die: the stream just goes quiet. Ziggy's travel calls take a
  // few seconds, so one still running well past that means no worker is answering. Temporal
  // retries it on the next worker once its 30-second start-to-close timeout passes.
  const STALLED_MS = 12_000;
  const TRAVEL_CALLS = new Set([
    "search_flights", "get_seat_map", "search_hotels", "book_flight", "select_seat", "book_hotel",
  ]);
  const runningSince = new Map<string, number>();
  let now = $state(Date.now());
  const running = $derived(
    Object.values(agent.agents).flatMap((view) =>
      view.messages.flatMap((m) =>
        m.parts.filter((p) => p.type === "tool" && p.state === "running" && TRAVEL_CALLS.has(p.toolName)),
      ),
    ) as { toolId: string }[],
  );
  $effect(() => {
    if (running.length === 0) return;
    const timer = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(timer);
  });
  const stalled = $derived(
    running.some(({ toolId }) => {
      if (!runningSince.has(toolId)) runningSince.set(toolId, Date.now());
      return now - runningSince.get(toolId)! > STALLED_MS;
    }),
  );

  // A message also stays "sending" until a worker accepts its Update, and the stream
  // reconnects when it can't reach the agent. Any of these lasting long enough to notice
  // means no worker is answering.
  //
  // Except while a model call runs: the model can be silent for minutes, and a quiet stream
  // is then just Ziggy thinking (the chat says so). Past the Gemini activity's 3-minute
  // start-to-close timeout, a call still showing as running does mean no worker finished it.
  const MODEL_TIMEOUT_MS = 200_000;
  let modelSince = $state<number | null>(null);
  const thinking = $derived(
    Object.values(agent.agents).some((view) =>
      view.messages.some((m) => m.parts.some((p) => p.type === "model_interaction" && p.status === "running")),
    ),
  );
  $effect(() => {
    if (!thinking) {
      modelSince = null;
      return;
    }
    modelSince ??= Date.now();
    const timer = setInterval(() => (now = Date.now()), 1000);
    return () => clearInterval(timer);
  });
  const quietForModel = $derived(thinking && modelSince !== null && now - modelSince < MODEL_TIMEOUT_MS);
  const waiting = $derived(
    stalled ||
      (!quietForModel && (agent.connection === "connecting" || agent.connection === "reconnecting")) ||
      agent.pending.some((message) => message.status === "sending"),
  );
  let away = $state(false);
  $effect(() => {
    if (!waiting) {
      away = false;
      return;
    }
    const timer = setTimeout(() => (away = true), 1500);
    return () => clearTimeout(timer);
  });

  // A trip ends when its agent closes itself after sitting idle (SESSION_IDLE_CLOSE_MINUTES), or
  // at its execution timeout. The client sees that when it reattaches, but while the agent is
  // idle it only asks whether new work arrived, so the page also checks the workflow itself
  // now and then and whenever the tab comes back. `ending` is what that check found.
  let ending = $state<{ status: string; reason: string | null } | null>(null);
  const ended = $derived(agent.connection === "closed" || ending !== null);
  const endReason = $derived.by(() => {
    const root = agent.rootAgentId ? agent.agents[agent.rootAgentId] : undefined;
    const reason = root?.closeReason ?? ending?.reason ?? null;
    if (reason === "idle_timeout_expired") return "idle";
    if (reason === "requested") return "requested";
    return ending?.status === "TIMED_OUT" ? "timeout" : "other";
  });
  async function noticeEnd(): Promise<boolean> {
    const state = await transport.workflowStatus(sessionId);
    if (!state.closed) return false;
    // A closed agent still answers its status query, whose `close_reason` says why it closed.
    // The client's snapshot type leaves that field out, though the response carries it.
    const reason = await transport.agentStatus(sessionId).then(
      (status) => (status as { close_reason?: string | null }).close_reason ?? null,
      () => null,
    );
    ending = { status: state.execution_status, reason };
    return true;
  }
  $effect(() => {
    if (agent.connection !== "idle") return;
    const check = () => {
      if (!document.hidden) noticeEnd().catch(() => {}); // a failed check is not news
    };
    const timer = setInterval(check, 30_000);
    document.addEventListener("visibilitychange", check);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", check);
    };
  });
  // A send that fails may be the first sign the trip has ended.
  $effect(() => {
    if (!agent.error || ended) return;
    noticeEnd().then(
      (closed) => {
        if (closed) agent.clearError();
      },
      () => {},
    );
  });

  const rows = $derived(departures(Object.values(agent.agents), board));
  // Choices waiting on the traveler, from Ziggy or any subagent, take over the chat column
  // until they're answered; the chat comes back, scrolled to the newest, once they are.
  const choices = $derived(agent.pendingCallbacks.filter((c) => isChoiceTool(c.part.toolName)));
  const still = $derived(motion.paused || motion.reduced);

  let draft = $state("");

  function send(event: SubmitEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    draft = "";
    // The message shows at once from `pending`; the server's reply reconciles it.
    void agent.sendMessage("ask", { text });
  }
</script>

<main class="workspace">
  <div class="travel">
    <RouteMap {rows} {away} />
    <Departures {rows} {board} {away} {still} />
  </div>

  <div class="side">
    {#if ended}
      <div class="card ended" role="status">
        <span class="badge idle">trip closed</span>
        <p>
          {#if endReason === "idle"}
            Ziggy closed this trip after it sat idle without a message.
          {:else if endReason === "timeout"}
            This trip reached its time limit and closed.
          {:else if endReason === "requested"}
            This trip was ended.
          {:else}
            This trip has closed.
          {/if}
          Its conversation and bookings stay here and in the Temporal UI. To keep planning, start a new trip.
        </p>
        <button class="button small primary ultraviolet" onclick={newTrip}>Start a new trip</button>
      </div>
    {:else if away}
      <div class="card recovering" role="status">
        <span class="badge progress">reconnecting</span>
        <p>
          Ziggy's worker isn't answering right now. Everything Ziggy has already accepted, including
          the trip, the conversation, and any approvals, is saved in Temporal. Ziggy carries on from
          the same step once a worker is running, and picks up a message that's still sending.
        </p>
      </div>
    {/if}
    {#if agent.error && !ended}
      <div class="card failure" role="alert">
        <span class="badge error">error</span>
        <p>{agent.error.message}</p>
        <button class="button small secondary ultraviolet" onclick={() => agent.clearError()}>Dismiss</button>
      </div>
    {/if}

    {#if choices.length > 0 && !ended}
      <section class="card choosing" aria-label="Choose an option">
        {#each choices as call (call.part.toolId)}
          <ChoiceCards part={call.part} answer={(choice) => agent.provideToolOutput(call.part.toolId, choice)} />
        {/each}
      </section>
    {:else}
      <Conversation {messages} />
    {/if}

    {#if agent.pendingApprovals.length > 0 && !ended}
      <div class="approvals">
        <ApprovalQueue
          calls={agent.pendingApprovals}
          respond={(call, decision) => agent.respondToApproval(call.part.toolId, decision)}
        />
      </div>
    {/if}

    {#if choices.length === 0 && !ended}
      <Settings
        {model}
        {policy}
        setModel={(next) => void agent.sendMessage("set_model", { model: next })}
        setPolicy={(next) => void agent.sendMessage("set_approval_policy", { new_policy: next })}
      />

      <form class="composer" onsubmit={send}>
        <label class="visually-hidden" for="composer">Message Ziggy</label>
        <textarea
          id="composer"
          rows="2"
          placeholder="Where are you going?"
          bind:value={draft}
          onkeydown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        ></textarea>
        <button class="button primary ultraviolet" type="submit" disabled={!draft.trim()}>Send</button>
      </form>
    {/if}
  </div>
</main>

<style>
  .workspace {
    flex: 1; min-height: 0; display: grid; gap: 1rem;
    grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
  }
  .travel { display: grid; grid-template-rows: minmax(12rem, 1fr) minmax(14rem, 1.15fr); gap: 1rem; min-height: 0; }
  .side { display: flex; flex-direction: column; gap: .8rem; min-height: 0; }
  .side > * { flex-shrink: 0; }
  .side > :global(.conversation), .side > .choosing { flex: 1 1 0; min-height: 8rem; }
  /* However many calls wait at once, the conversation keeps its share of the column. */
  .approvals { max-height: 55%; overflow: auto; flex-shrink: 1; min-height: 0; }
  .choosing { overflow: auto; display: grid; gap: 1.5rem; align-content: start; border-color: var(--yellow); }
  .recovering { border-color: var(--yellow); display: grid; gap: .5rem; }
  .ended { display: grid; gap: .5rem; justify-items: start; }
  .ended p { margin: 0; }
  .failure { border-color: var(--red); display: grid; gap: .5rem; justify-items: start; }
  .recovering p, .failure p { margin: 0; }
  .composer { display: flex; gap: .6rem; align-items: stretch; }
  textarea {
    flex: 1; resize: none; padding: .7rem .8rem; font: inherit; color: var(--off-white);
    background: rgba(20, 20, 20, .9); border: 1px solid var(--border);
  }
  textarea:focus-visible { outline: none; border-color: var(--green); box-shadow: 0 0 0 2px var(--green-soft); }
  @media (max-width: 900px) {
    .workspace { grid-template-columns: 1fr; grid-auto-rows: auto; }
    /* Stacked, the page scrolls, so give each column a screen's worth of height of its own:
       the conversation then scrolls inside it, as it does side by side. */
    .travel { height: min(90dvh, 48rem); }
    .side { height: min(90dvh, 52rem); }
  }
</style>
