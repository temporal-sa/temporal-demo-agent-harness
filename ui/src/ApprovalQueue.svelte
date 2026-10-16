<script lang="ts">
  import type { ToolApprovalDecision, WaitingToolCall } from "@temporalio/agent-harness-client";
  import ApprovalCard from "./ApprovalCard.svelte";
  import { callSummary, toolLabel } from "./format.ts";

  let {
    calls,
    respond,
  }: {
    calls: readonly WaitingToolCall[];
    respond: (call: WaitingToolCall, decision: ToolApprovalDecision) => Promise<unknown>;
  } = $props();

  // Scripts deserve a full read, one at a time. Everything else is grouped by agent and tool,
  // because a script that gathers its calls asks about them all at once.
  const scripts = $derived(calls.filter((c) => typeof c.part.input.script === "string"));
  const groups = $derived.by(() => {
    const byTool = new Map<string, WaitingToolCall[]>();
    for (const call of calls) {
      if (typeof call.part.input.script === "string") continue;
      const key = `${call.agentId}:${call.part.toolName}`;
      byTool.set(key, [...(byTool.get(key) ?? []), call]);
    }
    return [...byTool.entries()];
  });

  let sending = $state(new Set<string>());

  async function decide(batch: readonly WaitingToolCall[], decision: ToolApprovalDecision) {
    const ids = batch.map((c) => c.part.toolId);
    sending = new Set([...sending, ...ids]);
    try {
      // "Always allow" needs only one decision: the agent allow-lists the tool and approves
      // every other waiting call of it. Otherwise each call gets its own, sent together.
      if (decision.remember) await respond(batch[0], decision);
      else await Promise.all(batch.map((call) => respond(call, decision)));
    } finally {
      sending = new Set([...sending].filter((id) => !ids.includes(id)));
    }
  }
</script>

<div class="queue">
  {#each scripts as call (call.part.toolId)}
    <ApprovalCard {call} respond={(decision) => respond(call, decision)} />
  {/each}

  {#each groups as [key, group] (key)}
    {#if group.length === 1 && scripts.length === 0 && groups.length === 1}
      <ApprovalCard call={group[0]} respond={(decision) => respond(group[0], decision)} />
    {:else}
      {@const busy = group.some((c) => sending.has(c.part.toolId))}
      <article class="card group" aria-label="{group.length} {toolLabel(group[0].part.toolName)} calls need approval">
        <header>
          <span class="badge progress">needs your approval</span>
          <h3 class="heading">{toolLabel(group[0].part.toolName)} <span class="count mono">× {group.length}</span></h3>
        </header>
        <p class="muted">
          Monty's script runs these at the same time, each as its own Temporal Activity. They wait,
          durably, until you decide.
        </p>
        <div class="actions">
          <button class="button small primary green" disabled={busy} onclick={() => decide(group, { approved: true })}>
            Approve all {group.length}
          </button>
          <button
            class="button small secondary green"
            disabled={busy}
            title="Approve these, and don't ask about {group[0].part.toolName} again in this session"
            onclick={() => decide(group, { approved: true, remember: true })}
          >
            Always allow
          </button>
          <button class="button small secondary ultraviolet" disabled={busy} onclick={() => decide(group, { approved: false })}>
            Decline all
          </button>
        </div>
        <ul class="calls">
          {#each group as call (call.part.toolId)}
            {@const pending = sending.has(call.part.toolId)}
            <li>
              <span class="mono summary">{callSummary(call.part.toolName, call.part.input)}</span>
              <button class="tick" disabled={pending} aria-label="Approve {callSummary(call.part.toolName, call.part.input)}" onclick={() => decide([call], { approved: true })}>✓</button>
              <button class="cross" disabled={pending} aria-label="Decline {callSummary(call.part.toolName, call.part.input)}" onclick={() => decide([call], { approved: false })}>✕</button>
            </li>
          {/each}
        </ul>
      </article>
    {/if}
  {/each}
</div>

<style>
  .queue { display: grid; gap: .6rem; }
  .group { border-color: var(--yellow); display: grid; gap: .55rem; }
  .group:hover { border-color: var(--yellow); }
  header { display: flex; align-items: center; gap: .7rem; }
  .count { color: var(--yellow); font-size: .9rem; }
  p { margin: 0; }
  .actions { display: flex; flex-wrap: wrap; gap: .5rem; }
  .calls { list-style: none; margin: 0; padding: 0; display: grid; gap: .2rem; max-height: 11rem; overflow: auto; }
  li { display: flex; align-items: center; gap: .5rem; font-size: .8rem; padding: .15rem .3rem; background: rgba(13, 13, 20, .6); }
  .summary { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li button {
    font: 600 .8rem var(--font-mono); width: 1.8rem; height: 1.6rem; cursor: pointer;
    background: var(--space-black); color: var(--off-white); border: 1px solid var(--slate-500);
  }
  li .tick:hover:not(:disabled) { border-color: var(--green); color: var(--green); }
  li .cross:hover:not(:disabled) { border-color: var(--indigo-200); color: var(--indigo-200); }
  li button:disabled { opacity: .4; cursor: wait; }
  li button:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--green-soft); }
</style>
