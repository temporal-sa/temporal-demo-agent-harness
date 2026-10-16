<script lang="ts">
  import { AgentSession } from "@temporalio/agent-harness-svelte";
  import type { MontyChatAgent, TripBoard as Board } from "./generated/MontyChatAgent.ts";
  import ApprovalQueue from "./ApprovalQueue.svelte";
  import Conversation from "./Conversation.svelte";
  import { MODELS, type Model, type Policy } from "./format.ts";
  import Settings from "./Settings.svelte";
  import Departures from "./Departures.svelte";
  import { motion } from "./motion.svelte.ts";
  import RouteMap from "./RouteMap.svelte";
  import { departures } from "./travel.ts";

  let { sessionId }: { sessionId: string } = $props();

  const agent = new AgentSession<MontyChatAgent>({
    get sessionId() {
      return sessionId;
    },
  });

  // The board lives on whichever agent in the tree runs the scripts: the root for Monty
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

  // The page can't see a worker die: the stream just goes quiet. Monty's travel calls take a
  // few seconds, so one still running well past that means no worker is answering. Temporal
  // retries it on the next worker once its 30-second start-to-close timeout passes.
  const STALLED_MS = 12_000;
  const TRAVEL_CALLS = new Set(["search_flights", "search_hotels", "book_flight", "book_hotel"]);
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
  const waiting = $derived(
    stalled ||
      agent.connection === "connecting" ||
      agent.connection === "reconnecting" ||
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

  const rows = $derived(departures(Object.values(agent.agents), board));
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
    {#if away}
      <div class="card recovering" role="status">
        <span class="badge progress">reconnecting</span>
        <p>
          Monty's worker isn't answering right now. Everything Monty has already accepted, including
          the trip, the conversation, and any approvals, is saved in Temporal. Monty carries on from
          the same step once a worker is running, and picks up a message that's still sending.
        </p>
      </div>
    {/if}
    {#if agent.error}
      <div class="card failure" role="alert">
        <span class="badge error">error</span>
        <p>{agent.error.message}</p>
        <button class="button small secondary ultraviolet" onclick={() => agent.clearError()}>Dismiss</button>
      </div>
    {/if}

    <Conversation {messages} />

    {#if agent.pendingApprovals.length > 0}
      <div class="approvals">
        <ApprovalQueue
          calls={agent.pendingApprovals}
          respond={(call, decision) => agent.respondToApproval(call.part.toolId, decision)}
        />
      </div>
    {/if}

    <Settings
      {model}
      {policy}
      setModel={(next) => void agent.sendMessage("set_model", { model: next })}
      setPolicy={(next) => void agent.sendMessage("set_approval_policy", { new_policy: next })}
    />

    <form class="composer" onsubmit={send}>
      <label class="visually-hidden" for="composer">Message Monty</label>
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
  .side > :global(.conversation) { flex: 1 1 0; min-height: 8rem; }
  /* However many calls wait at once, the conversation keeps its share of the column. */
  .approvals { max-height: 55%; overflow: auto; flex-shrink: 1; min-height: 0; }
  .recovering { border-color: var(--yellow); display: grid; gap: .5rem; }
  .failure { border-color: var(--red); display: grid; gap: .5rem; justify-items: start; }
  .recovering p, .failure p { margin: 0; }
  .composer { display: flex; gap: .6rem; align-items: stretch; }
  textarea {
    flex: 1; resize: none; padding: .7rem .8rem; font: inherit; color: var(--off-white);
    background: rgba(20, 20, 20, .9); border: 1px solid var(--border);
  }
  textarea:focus-visible { outline: none; border-color: var(--green); box-shadow: 0 0 0 2px var(--green-soft); }
  @media (max-width: 900px) {
    .workspace { grid-template-columns: 1fr; grid-auto-rows: minmax(18rem, auto); }
  }
</style>
