<script lang="ts">
  import Code from "./Code.svelte";
  import { markdown, type Inline } from "./markdown.ts";

  let { source }: { source: string } = $props();
  const blocks = $derived(markdown(source));
</script>

{#snippet spans(pieces: Inline[])}
  {#each pieces as piece, i (i)}
    {#if piece.style === "bold"}<strong>{piece.text}</strong>
    {:else if piece.style === "italic"}<em>{piece.text}</em>
    {:else if piece.style === "code"}<code>{piece.text}</code>
    {:else}{piece.text}{/if}
  {/each}
{/snippet}

<div class="md">
  {#each blocks as block, i (i)}
    {#if block.kind === "heading"}
      <p class="heading-{Math.min(block.level, 3)}">{@render spans(block.text)}</p>
    {:else if block.kind === "code"}
      <Code code={block.text} language={block.language} max="20rem" />
    {:else if block.kind === "rule"}
      <hr />
    {:else if block.kind === "list"}
      <svelte:element this={block.ordered ? "ol" : "ul"}>
        {#each block.items as item, j (j)}<li>{@render spans(item)}</li>{/each}
      </svelte:element>
    {:else}
      <p>
        {#each block.lines as line, j (j)}{#if j > 0}<br />{/if}{@render spans(line)}{/each}
      </p>
    {/if}
  {/each}
</div>

<style>
  .md { display: grid; gap: .5rem; }
  p, ul, ol { margin: 0; }
  ul, ol { padding-left: 1.2rem; display: grid; gap: .2rem; }
  .heading-1, .heading-2, .heading-3 { font-weight: 500; color: var(--indigo-100); margin-top: .3rem; }
  .heading-1 { font-size: 1.15rem; }
  .heading-2 { font-size: 1.05rem; }
  hr { border: 0; border-top: 1px solid var(--border); margin: .2rem 0; width: 100%; }
  em { color: var(--indigo-100); }
  code { font-family: var(--font-mono); font-size: .85em; padding: 0 .25em; background: #0d0d14; }
</style>
