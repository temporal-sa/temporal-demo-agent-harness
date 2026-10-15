<script lang="ts">
  import { AgentSession } from "@temporalio/agent-harness-svelte";
  import type { MontyChatAgent, TripBoard as Board } from "./generated/MontyChatAgent.ts";
  import ApprovalCard from "./ApprovalCard.svelte";
  import Conversation from "./Conversation.svelte";
  import TripBoard from "./TripBoard.svelte";

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

  // A message stays "sending" until a worker accepts its Update, and the stream reconnects
  // when it can't reach the agent. Either one lasting long enough to notice means no worker
  // is answering.
  const waiting = $derived(
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
  <TripBoard {board} />

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

    {#each agent.pendingApprovals as call (call.part.toolId)}
      <ApprovalCard {call} respond={(approved) => agent.respondToApproval(call.part.toolId, { approved })} />
    {/each}

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
  .side { display: flex; flex-direction: column; gap: .8rem; min-height: 0; }
  .side > :global(.conversation) { flex: 1; }
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
