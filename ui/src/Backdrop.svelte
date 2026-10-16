<script lang="ts">
  // The Temporal backdrop from the demo buildkit: a drifting starfield, the perspective grid
  // floor, and the slow glow blobs, all fixed behind the page. The header's Pause motion
  // control stills them (the CSS side keys off `.motion-paused` on the app).
  import { motion } from "./motion.svelte.ts";
  import { startStarfield } from "./starfield.ts";

  let canvas: HTMLCanvasElement | undefined = $state();
  let field: ReturnType<typeof startStarfield> | undefined;

  $effect(() => {
    if (!canvas) return;
    field = startStarfield(canvas);
    return () => field?.stop();
  });
  $effect(() => {
    field?.setPaused(motion.paused || motion.reduced);
  });
</script>

<canvas id="stars" aria-hidden="true" bind:this={canvas}></canvas>
<div class="grid-floor" aria-hidden="true"></div>
<div class="blur-container" aria-hidden="true">
  <div class="blur-pink"></div>
  <div class="blur-yellow"></div>
  <div class="blur-green"></div>
</div>
