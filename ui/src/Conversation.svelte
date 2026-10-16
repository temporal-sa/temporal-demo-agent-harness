<script lang="ts">
  import type { HarnessMessage, MessagePart, ToolPart } from "@temporalio/agent-harness-client";
  import { policyLabel, toolBadge, toolLabel } from "./format.ts";
  import Code from "./Code.svelte";
  import Markdown from "./Markdown.svelte";
  import type { MontyChatAgent } from "./generated/MontyChatAgent.ts";

  type Message = HarnessMessage<MontyChatAgent>;
  /** A message's parts in the order they streamed, with adjacent text deltas joined. */
  type Segment =
    | { kind: "text"; text: string }
    | { kind: "thought"; text: string }
    | { kind: "part"; part: MessagePart }
    /** Several calls of one tool in a row, as a gathered script makes them. */
    | { kind: "tools"; name: string; parts: ToolPart[] };

  let { messages }: { messages: readonly Message[] } = $props();

  let scroller: HTMLElement | undefined = $state();
  // Follow the newest content until the reader scrolls up to read; scrolling back to the
  // bottom, or sending a message, follows again.
  let pinned = true;

  function onscroll() {
    if (!scroller) return;
    pinned = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 48;
  }

  $effect(() => {
    if (!scroller) return;
    const list = scroller;
    const follow = () => {
      if (pinned) list.scrollTop = list.scrollHeight;
    };
    // Any growth counts: a streamed word, a tool step, a code block opening, a reflow.
    const mutations = new MutationObserver(follow);
    mutations.observe(list, { childList: true, subtree: true, characterData: true });
    const resizes = new ResizeObserver(follow);
    resizes.observe(list);
    follow();
    return () => {
      mutations.disconnect();
      resizes.disconnect();
    };
  });

  let seen = 0;
  $effect(() => {
    // A message the reader just sent brings the view back to the bottom.
    if (messages.length > seen && messages.at(-1)?.status === "sending") pinned = true;
    seen = messages.length;
  });

  function segments(message: Message): Segment[] {
    const out: Segment[] = [];
    for (const part of message.parts) {
      const last = out.at(-1);
      if (part.type === "reply_delta") {
        if (last?.kind === "text") last.text += part.text;
        else out.push({ kind: "text", text: part.text });
      } else if (part.type === "thought_summary") {
        if (last?.kind === "thought") last.text += part.text;
        else out.push({ kind: "thought", text: part.text });
      } else if (part.type === "tool" && typeof part.input.script !== "string") {
        const prev = last?.kind === "part" && last.part.type === "tool" ? last.part : null;
        if (last?.kind === "tools" && last.name === part.toolName) last.parts.push(part);
        else if (prev && prev.toolName === part.toolName && typeof prev.input.script !== "string") {
          out[out.length - 1] = { kind: "tools", name: part.toolName, parts: [prev, part] };
        } else out.push({ kind: "part", part });
      } else if (part.type !== "text_annotation") {
        out.push({ kind: "part", part });
      }
    }
    // A reply that arrived whole rather than streamed.
    if (!out.some((s) => s.kind === "text") && message.output?.text) {
      out.push({ kind: "text", text: message.output.text });
    }
    return out;
  }

  /** A one-line label for a settings change, or null for any other message. */
  /** How many of a group of calls are in each state, busiest first. */
  function tally(parts: ToolPart[]): [string, string, number][] {
    const counts = new Map<string, [string, string, number]>();
    for (const part of parts) {
      const { label, tone } = toolBadge(part.state);
      const entry = counts.get(label) ?? [label, tone, 0];
      entry[2] += 1;
      counts.set(label, entry);
    }
    return [...counts.values()].sort((a, b) => b[2] - a[2]);
  }

  function setting(message: Message): string | null {
    if (message.handler === "set_model") return `Model → ${message.input.model}`;
    if (message.handler === "set_approval_policy") return `Approvals → ${policyLabel(message.input.new_policy)}`;
    return null;
  }

  /** A message to a handler this view doesn't send, such as a script sent from the console. */
  function other(message: Message): { code: string; language: string } {
    const input: Record<string, unknown> = { ...message.input };
    return typeof input.script === "string"
      ? { code: input.script, language: "python" }
      : { code: JSON.stringify(input, null, 2), language: "json" };
  }

  const tokens = new Intl.NumberFormat("en-US", { notation: "compact" });
</script>

<section class="card conversation" aria-labelledby="chat-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="chat-title">Conversation</h2>
    <span class="muted">Each message is a Workflow Update</span>
  </header>

  <ol class="messages" bind:this={scroller} {onscroll} aria-live="polite">
    {#if messages.length === 0}
      <li class="hint muted">
        Try: <em>“Fly Ada Lovelace from SFO to JFK on November 3, back on the 7th, and find a hotel near Central Park.”</em>
      </li>
    {/if}
    {#each messages as message (message.id)}
      {@const label = setting(message)}
      {#if label}
        <li class="setting mono">
          <span>{label}</span>
          {#if message.status === "error"}
            <span class="failure">{message.error}</span>
          {:else if message.status === "done"}
            <span class="badge good">applied</span>
          {:else}
            <span class="badge progress">{message.status === "sending" ? "sending" : "applying"}</span>
          {/if}
        </li>
      {:else}
        <li class="turn">
          {#if message.handler === "ask"}
            <p class="you">{message.input.text}</p>
          {:else}
            <div class="you sent-other">
              <span class="eyebrow">{message.handler}</span>
              <Code {...other(message)} max="10rem" />
            </div>
          {/if}

          {#each segments(message) as segment, i (i)}
            {#if segment.kind === "text"}
              <div class="monty"><Markdown source={segment.text} /></div>
            {:else if segment.kind === "thought"}
              <p class="thought">{segment.text}</p>
            {:else if segment.kind === "tools"}
              <div class="activity">
                {#each tally(segment.parts) as [label, tone, count] (label)}
                  <span class="badge {tone}">{count} {label}</span>
                {/each}
                <span class="mono">{toolLabel(segment.name)} <span class="muted">× {segment.parts.length}</span></span>
                {#if segment.parts.some((p) => p.approval?.remember)}
                  <span class="muted">· always allowed from now on</span>
                {/if}
              </div>
            {:else if segment.part.type === "model_interaction"}
              {@const call = segment.part}
              <div class="activity model">
                {#if call.status === "running"}
                  <span class="badge progress">thinking</span>
                  <span class="mono thinking">{call.model ?? "model"}</span>
                {:else}
                  <span class="badge idle">model call</span>
                  <span class="mono muted">
                    {call.model ?? "model"}{call.usage?.total_tokens ? ` · ${tokens.format(call.usage.total_tokens)} tokens` : ""}
                  </span>
                {/if}
              </div>
            {:else if segment.part.type === "tool"}
              {@const tool = segment.part}
              {@const badge = toolBadge(tool.state)}
              <div class="activity">
                <span class="badge {badge.tone}">{badge.label}</span>
                <span class="mono">{toolLabel(tool.toolName)}</span>
                {#if tool.approval?.remember}
                  <span class="muted">· always allowed from now on</span>
                {/if}
                {#if typeof tool.input.script === "string"}
                  <details>
                    <summary class="muted">script</summary>
                    <Code code={tool.input.script} max="12rem" />
                  </details>
                {/if}
                {#if tool.state === "failed" && tool.error}
                  <span class="muted">{tool.error}</span>
                {/if}
              </div>
            {:else if segment.part.type === "subagent"}
              {@const sub = segment.part}
              <div class="activity">
                <span class="badge {sub.status === 'error' ? 'error' : sub.status === 'running' ? 'progress' : 'good'}">
                  {sub.status}
                </span>
                <span class="mono">Subagent {sub.agentKey} · {sub.handler}</span>
              </div>
            {/if}
          {/each}

          {#if message.status === "sending"}
            <p class="muted">Sending…</p>
          {:else if message.status === "accepted"}
            <p class="muted">Received. Monty will pick it up in order.</p>
          {:else if message.status === "running" && message.parts.length === 0}
            <p class="muted thinking">Monty is working…</p>
          {/if}
          {#if message.status === "error" && message.error}
            <p class="failure">{message.error}</p>
          {/if}
        </li>
      {/if}
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
  .sent-other :global(.code) { margin-top: .3rem; background: rgba(13, 13, 20, .7); }
  .setting { display: flex; gap: .6rem; align-items: center; justify-content: center; font-size: .75rem; color: var(--indigo-100); }
  .activity { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center; font-size: .82rem; }
  .model { font-size: .75rem; }
  details { flex-basis: 100%; }
  details :global(.code) { margin-top: .3rem; }
  summary { cursor: pointer; }
  .thought { margin: 0; padding-left: .7rem; border-left: 2px solid var(--slate-500); color: var(--slate-300); font-style: italic; font-size: .85rem; white-space: pre-wrap; }
  .thinking { animation: breathe 1.6s ease-in-out infinite; }
  .failure { margin: 0; color: var(--red); }
  .hint { padding: 1rem 0; }
  @keyframes breathe { 50% { opacity: .45; } }
</style>
