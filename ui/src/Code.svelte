<script lang="ts">
  import { highlight } from "./highlight.ts";

  let { code, language = "python", max = "14rem" }: { code: string; language?: string; max?: string } =
    $props();

  const html = $derived(highlight(code.replace(/^\n+|\s+$/g, ""), language));
</script>

<!-- highlight.js escapes the code before adding its spans, so this can't inject markup. -->
<pre class="code mono" style:max-height={max}><code>{@html html}</code></pre>

<style>
  .code {
    margin: 0; padding: .7rem .8rem; overflow: auto; font-size: .75rem; line-height: 1.5;
    background: #0d0d14; border: 1px solid var(--border); color: var(--off-white); white-space: pre;
  }
  /* Temporal palette, without red: red is reserved for errors on this page. */
  .code :global(.hljs-keyword),
  .code :global(.hljs-built_in),
  .code :global(.hljs-literal) { color: var(--purple); }
  .code :global(.hljs-string),
  .code :global(.hljs-attr) { color: var(--green); }
  .code :global(.hljs-number) { color: var(--yellow); }
  .code :global(.hljs-title),
  .code :global(.hljs-title.function_) { color: var(--cyan); }
  .code :global(.hljs-params),
  .code :global(.hljs-variable) { color: var(--indigo-100); }
  .code :global(.hljs-comment) { color: var(--slate-300); font-style: italic; }
  .code :global(.hljs-meta),
  .code :global(.hljs-punctuation) { color: var(--indigo-200); }
</style>
