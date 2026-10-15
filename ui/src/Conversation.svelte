<script lang="ts">
  import type { HarnessMessage, MessagePart } from "@temporalio/agent-harness-client";
  import { emphasis, toolBadge, toolLabel } from "./format.ts";
  import type { MontyChatAgent } from "./generated/MontyChatAgent.ts";

  type Message = HarnessMessage<MontyChatAgent>;

  let { messages }: { messages: readonly Message[] } = $props();

  let scroller: HTMLElement | undefined = $state();
  let opened = false;

  // Open at the newest turn, then follow new content while the reader stays at the bottom.
  $effect(() => {
    void messages.length;
    void messages.at(-1)?.parts.length;
    if (!scroller) return;
    const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
    if (nearBottom || !opened) queueMicrotask(() => scroller?.scrollTo({ top: scroller.scrollHeight }));
    if (messages.length > 0) opened = true;
  });

  /** A message to any handler other than `ask`, such as a script sent from the console. */
  function other(message: Message): string {
    const input: Record<string, unknown> = { ...message.input };
    return typeof input.script === "string" ? input.script : JSON.stringify(input, null, 2);
  }

  function reply(message: Message): string {
    if (message.output?.text) return message.output.text;
    return message.parts
      .filter((part): part is Extract<MessagePart, { type: "reply_delta" }> => part.type === "reply_delta")
      .map((part) => part.text)
      .join("");
  }
</script>

<section class="card conversation" aria-labelledby="chat-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="chat-title">Conversation</h2>
    <span class="muted">Each turn is a Workflow Update</span>
  </header>

  <ol class="messages" bind:this={scroller} aria-live="polite">
    {#if messages.length === 0}
      <li class="hint muted">
        Try: <em>“Fly Ada Lovelace from SFO to JFK on November 3, back on the 7th, and find a hotel near Central Park.”</em>
      </li>
    {/if}
    {#each messages as message (message.id)}
      <li class="turn">
        {#if message.handler === "ask"}
          <p class="you">{message.input.text}</p>
        {:else}
          <div class="you sent-other">
            <span class="eyebrow">{message.handler}</span>
            <pre class="mono">{other(message)}</pre>
          </div>
        {/if}

        {#each message.parts as part, i (i)}
          {#if part.type === "tool"}
            {@const badge = toolBadge(part.state)}
            <div class="activity">
              <span class="badge {badge.tone}">{badge.label}</span>
              <span class="mono">{toolLabel(part.toolName)}</span>
              {#if typeof part.input.script === "string"}
                <details>
                  <summary class="muted">script</summary>
                  <pre class="mono">{part.input.script}</pre>
                </details>
              {/if}
              {#if part.state === "failed" && part.error}
                <span class="muted">{part.error}</span>
              {/if}
            </div>
          {:else if part.type === "subagent"}
            <div class="activity">
              <span class="badge {part.status === 'error' ? 'error' : part.status === 'running' ? 'progress' : 'good'}">
                {part.status}
              </span>
              <span class="mono">Subagent {part.agentKey} · {part.handler}</span>
            </div>
          {/if}
        {/each}

        {#if reply(message)}
          <div class="monty">
            {#each reply(message).split(/\n{2,}/) as paragraph, i (i)}
              <p>
                {#each emphasis(paragraph) as segment, j (j)}
                  {#if segment.bold}<strong>{segment.text}</strong>{:else}{segment.text}{/if}
                {/each}
              </p>
            {/each}
          </div>
        {:else if message.status === "sending"}
          <p class="muted">Sending…</p>
        {:else if message.status === "accepted"}
          <p class="muted">Received. Monty will pick it up in order.</p>
        {:else if message.status === "running"}
          <p class="muted thinking">Monty is working…</p>
        {/if}
        {#if message.status === "error" && message.error}
          <p class="failure">{message.error}</p>
        {/if}
      </li>
    {/each}
  </ol>
</section>

<style>
  .conversation { display: flex; flex-direction: column; gap: .8rem; min-height: 0; }
  .messages { list-style: none; margin: 0; padding: 0 .2rem 0 0; overflow: auto; display: grid; gap: 1.2rem; align-content: start; flex: 1; }
  .turn { display: grid; gap: .5rem; }
  .you {
    margin: 0; justify-self: end; max-width: 85%; padding: .55rem .8rem;
    background: rgba(68, 76, 231, .25); border: 1px solid var(--uv);
  }
  .sent-other pre { margin: .3rem 0 0; font-size: .72rem; white-space: pre-wrap; max-height: 10rem; overflow: auto; }
  .activity { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; font-size: .82rem; }
  details { flex-basis: 100%; }
  details pre { margin: .3rem 0 0; padding: .6rem; font-size: .72rem; background: #0d0d14; border: 1px solid var(--border); overflow: auto; max-height: 12rem; }
  summary { cursor: pointer; }
  .monty p { margin: 0 0 .5rem; white-space: pre-wrap; }
  .thinking { animation: breathe 1.6s ease-in-out infinite; }
  .failure { margin: 0; color: var(--red); }
  .hint { padding: 1rem 0; }
  @keyframes breathe { 50% { opacity: .45; } }
</style>
