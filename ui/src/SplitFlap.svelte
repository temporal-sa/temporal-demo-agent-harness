<script lang="ts">
  import { untrack } from "svelte";

  let {
    text,
    width,
    still = false,
  }: {
    text: string;
    /** Cells to show; longer text is cut, shorter text is padded. */
    width: number;
    /** Change at once, without flipping (reduced or paused motion). */
    still?: boolean;
  } = $props();

  const FLIPS = 5;
  const FLIP_MS = 45;
  const STAGGER_MS = 22;
  const CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

  const target = $derived(text.toUpperCase().padEnd(width).slice(0, width));
  let shown = $state<string[]>([]);

  // Each cell that changes flips through a few letters before it lands, left to right, like
  // an airport board. Cells that don't change stay put.
  $effect(() => {
    const next = target.split("");
    const current = untrack(() => shown);
    if (still || current.length === 0) {
      shown = next;
      return;
    }
    const timers: ReturnType<typeof setTimeout>[] = [];
    next.forEach((char, i) => {
      if (current[i] === char) return;
      for (let step = 0; step <= FLIPS; step++) {
        timers.push(
          setTimeout(() => {
            shown[i] = step === FLIPS ? char : CHARSET[Math.floor(Math.random() * CHARSET.length)];
          }, i * STAGGER_MS + step * FLIP_MS),
        );
      }
    });
    return () => timers.forEach(clearTimeout);
  });
</script>

<span class="flap" aria-label={text}>
  {#each shown as char, i (i)}
    <span class="cell" aria-hidden="true">
      {#key char}<span class="char" class:still>{char}</span>{/key}
    </span>
  {/each}
</span>

<style>
  .flap { display: inline-flex; gap: 2px; }
  .cell {
    position: relative; width: 1.05em; height: 1.45em; display: inline-grid; place-items: center;
    background: linear-gradient(#1c1c26 50%, #15151d 50%); border-radius: 2px;
    font-family: var(--font-mono); font-weight: 600; color: inherit; overflow: hidden;
    perspective: 200px;
  }
  .cell::after {
    content: ""; position: absolute; left: 0; right: 0; top: 50%; height: 1px; background: #050507;
  }
  .char { display: inline-block; animation: flip 90ms ease-out; transform-origin: 50% 100%; }
  .char.still { animation: none; }
  @keyframes flip { from { transform: rotateX(-90deg); } to { transform: rotateX(0deg); } }
</style>
