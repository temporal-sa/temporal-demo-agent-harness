<script lang="ts">
  import type { WaitingToolCall } from "@temporalio/agent-harness-client";
  import Code from "./Code.svelte";
  import { toolLabel } from "./format.ts";

  let {
    call,
    respond,
  }: {
    call: WaitingToolCall;
    respond: (decision: { approved: boolean; remember?: boolean }) => Promise<unknown>;
  } = $props();

  let sending = $state<"approve" | "always" | "decline" | null>(null);
  const script = $derived(typeof call.part.input.script === "string" ? call.part.input.script : null);
  const fields = $derived(Object.entries(call.part.input).filter(([key]) => key !== "script"));

  async function decide(choice: "approve" | "always" | "decline") {
    sending = choice;
    try {
      await respond({ approved: choice !== "decline", remember: choice === "always" });
    } finally {
      sending = null;
    }
  }
</script>

<article class="card approval" aria-label="Approval needed: {toolLabel(call.part.toolName)}">
  <header>
    <span class="badge progress">needs your approval</span>
    <h3 class="heading">{toolLabel(call.part.toolName)}</h3>
  </header>

  {#if script}
    <Code code={script} />
  {/if}
  {#if fields.length > 0}
    <dl class="fields">
      {#each fields as [key, value] (key)}
        <dt class="mono">{key}</dt>
        <dd>
          {#if typeof value === "string"}{value}{:else}<Code code={JSON.stringify(value, null, 2)} language="json" max="10rem" />{/if}
        </dd>
      {/each}
    </dl>
  {/if}

  <p class="muted">
    The Workflow is waiting on you, durably: close the tab or crash the worker and this request is
    still here. Approving runs it as a Temporal Activity.
  </p>
  <div class="actions">
    <button class="button small primary green" disabled={sending !== null} onclick={() => decide("approve")}>
      {sending === "approve" ? "Approving…" : "Approve"}
    </button>
    <button
      class="button small secondary green"
      disabled={sending !== null}
      title="Approve, and don't ask about {call.part.toolName} again in this session"
      onclick={() => decide("always")}
    >
      {sending === "always" ? "Approving…" : "Always allow"}
    </button>
    <button class="button small secondary ultraviolet" disabled={sending !== null} onclick={() => decide("decline")}>
      {sending === "decline" ? "Declining…" : "Decline"}
    </button>
  </div>
</article>

<style>
  .approval { border-color: var(--yellow); display: grid; gap: .6rem; }
  .approval:hover { border-color: var(--yellow); }
  header { display: flex; align-items: center; gap: .7rem; }
  .fields { display: grid; grid-template-columns: auto 1fr; gap: .2rem .8rem; margin: 0; font-size: .85rem; }
  dt { color: var(--indigo-100); font-size: .75rem; }
  dd { margin: 0; overflow-wrap: anywhere; }
  .actions { display: flex; gap: .6rem; }
  p { margin: 0; }
</style>
