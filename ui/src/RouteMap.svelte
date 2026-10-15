<script lang="ts">
  import { geoGraticule10, geoMercator, geoPath, type GeoProjection } from "d3-geo";
  import type { FeatureCollection, MultiLineString } from "geojson";
  import { AIRPORTS } from "./airports.ts";
  import ziggy from "./assets/ziggy-face.png";
  import { isMoving, type Row, type Stage } from "./travel.ts";

  let { rows, away, still }: { rows: Row[]; away: boolean; still: boolean } = $props();

  // The drawing matches the panel's size, so the map fills it without stretching.
  let width = $state(1000);
  let height = $state(520);
  const W = $derived(Math.max(width, 200));
  const H = $derived(Math.max(height, 160));
  const PAD = 70;

  const flights = $derived(rows.filter((r) => r.kind === "flight" && AIRPORTS[r.from] && AIRPORTS[r.to]));
  const hotels = $derived(rows.filter((r) => r.kind === "hotel"));
  const unmapped = $derived(rows.filter((r) => r.kind === "flight" && !(AIRPORTS[r.from] && AIRPORTS[r.to])));
  const codes = $derived([...new Set(flights.flatMap((r) => [r.from, r.to]))]);

  // Land and borders from Natural Earth (1:110m), loaded after the page so it never delays it.
  let land = $state<FeatureCollection | null>(null);
  let borders = $state<MultiLineString | null>(null);
  Promise.all([import("world-atlas/countries-110m.json"), import("topojson-client")]).then(
    ([atlas, topojson]) => {
      const topology = atlas.default as unknown as Parameters<typeof topojson.feature>[0];
      const objects = (topology as unknown as { objects: Record<string, never> }).objects;
      land = topojson.feature(topology, objects.land) as unknown as FeatureCollection;
      borders = topojson.mesh(topology, objects.countries, (a, b) => a !== b) as MultiLineString;
    },
  );

  // Mercator fitted to the airports in play, opened out to at least a region's width so a
  // short hop still shows the coastline around it. With no airports yet, most of the world.
  const projection: GeoProjection = $derived.by(() => {
    // Before any airports, the whole world, as wide as the panel, a little north of center.
    if (codes.length === 0) return geoMercator().scale(W / (2 * Math.PI)).translate([W / 2, H * 0.6]);
    const points = codes.map((c) => [AIRPORTS[c][1], AIRPORTS[c][0]]);
    const lons = points.map((p) => p[0]);
    const lats = points.map((p) => p[1]);
    const midLon = (Math.min(...lons) + Math.max(...lons)) / 2;
    const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
    points.push([midLon - 14, midLat - 8], [midLon + 14, midLat + 8]);
    return geoMercator().fitExtent(
      [[PAD, PAD], [W - PAD, H - PAD]],
      { type: "MultiPoint", coordinates: points },
    );
  });
  const path = $derived(geoPath(projection));
  const graticule = geoGraticule10();

  function project([lat, lon]: [number, number]): readonly [number, number] {
    const [x, y] = projection([lon, lat]) ?? [W / 2, H / 2];
    return [x, y];
  }

  function point(code: string) {
    return project(AIRPORTS[code]);
  }

  /** A shallow arc from one airport to another, bowed to the left of travel. Pass an
   *  origin to get the same arc relative to that point, for Ziggy's flight path. */
  function arc(from: string, to: string, [ox, oy]: readonly [number, number] = [0, 0]): string {
    const [x1, y1] = point(from);
    const [x2, y2] = point(to);
    const bow = 0.22;
    const cx = (x1 + x2) / 2 + (y2 - y1) * bow;
    const cy = (y1 + y2) / 2 - (x2 - x1) * bow;
    return `M ${x1 - ox} ${y1 - oy} Q ${cx - ox} ${cy - oy} ${x2 - ox} ${y2 - oy}`;
  }

  const TONE: Record<Stage, string> = {
    searching: "cyan", options: "slate", clearance: "yellow", boarding: "yellow",
    confirmed: "green", declined: "slate", failed: "red",
  };

  // Ziggy flies the leg Monty is working on, circles while no worker answers, and otherwise
  // waits where the trip last landed.
  const active = $derived(flights.findLast((r) => ["searching", "boarding", "clearance"].includes(r.stage)));
  const landed = $derived(flights.findLast((r) => r.stage === "confirmed"));
  const ziggyMode = $derived(
    away && rows.some((r) => isMoving(r.stage))
      ? "holding"
      : active
        ? active.stage === "clearance" ? "waiting" : "flying"
        : landed ? "parked" : "idle",
  );
  const ziggyAt = $derived.by(() => {
    if (ziggyMode === "parked" && landed) {
      const [x, y] = point(landed.to);
      return [x, y - 30] as const; // above the airport, clear of its label
    }
    if (active) return point(active.from);
    if (landed) return point(landed.to);
    return [W / 2, H / 2] as const;
  });
  const heading = $derived(active ? Math.sign(point(active.to)[0] - point(active.from)[0]) || 1 : 1);
  const caption = $derived(
    ziggyMode === "flying" && active
      ? `${active.stage === "searching" ? "Searching" : "Booking"} ${active.from} → ${active.to}`
      : ziggyMode === "waiting" && active
        ? `Waiting for clearance · ${active.from} → ${active.to}`
        : ziggyMode === "holding"
          ? "Holding · worker offline"
          : ziggyMode === "parked" && landed
            ? `Landed at ${landed.to}`
            : "Ready for departure",
  );

  // Stays are searched by city name, not airport, so each pin goes where the flight that
  // arrives on its check-in date lands, or the trip's last destination if none matches.
  const stays = $derived.by(() => {
    const placed = new Map<string, Row[]>();
    for (const stay of hotels) {
      const airport = flights.find((f) => stay.date && f.date === stay.date)?.to ?? flights.at(-1)?.to;
      if (airport) placed.set(airport, [...(placed.get(airport) ?? []), stay]);
    }
    return [...placed.entries()];
  });

  let svg: SVGSVGElement | undefined = $state();
  $effect(() => {
    if (!svg) return;
    if (still) svg.pauseAnimations();
    else svg.unpauseAnimations();
  });
</script>

<section class="card map" aria-labelledby="map-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="map-title">Route map</h2>
    <span class="muted">{caption}</span>
  </header>

  <div class="frame" bind:clientWidth={width} bind:clientHeight={height}>
  <svg bind:this={svg} viewBox="0 0 {W} {H}" width={W} height={H} role="img" aria-label="Route map. {caption}.">
    <defs>
      <clipPath id="cockpit"><circle cx="88" cy="16" r="10" /></clipPath>
      <radialGradient id="glow">
        <stop offset="0%" stop-color="rgba(68,76,231,.35)" />
        <stop offset="100%" stop-color="rgba(68,76,231,0)" />
      </radialGradient>
    </defs>
    <path class="graticule" d={path(graticule)} />
    {#if land}<path class="land" d={path(land)} />{/if}
    {#if borders}<path class="borders" d={path(borders)} />{/if}
    <circle cx={W / 2} cy={H / 2} r={H / 2} fill="url(#glow)" />

    {#each flights as leg (leg.key)}
      <path
        d={arc(leg.from, leg.to)}
        class="leg {TONE[leg.stage]}"
        class:dashed={leg.stage !== "confirmed"}
        class:moving={leg.stage === "searching" && !away}
      />
    {/each}

    {#each codes as code (code)}
      {@const [x, y] = point(code)}
      <g class="airport" transform="translate({x} {y})">
        <circle r="6" />
        <text y="-14">{code}</text>
      </g>
    {/each}

    {#each stays as [airport, list] (airport)}
      {@const [x, y] = point(airport)}
      {#each list as stay, i (stay.key)}
        <g class="hotel {TONE[stay.stage]}" transform="translate({x + 20 + i * 24} {y + 20})">
          <title>{stay.label || stay.from}</title>
          <rect x="-9" y="-9" width="18" height="18" rx="2" />
          <text y="4">H</text>
        </g>
      {/each}
    {/each}

    <g transform="translate({ziggyAt[0]} {ziggyAt[1]})">
      <g class="ziggy-pilot" class:holding={ziggyMode === "holding"}>
        {#if ziggyMode === "flying" && active}
          <animateMotion dur="3.2s" repeatCount="indefinite" path={arc(active.from, active.to, ziggyAt)} />
        {:else if ziggyMode === "holding"}
          <animateMotion dur="4s" repeatCount="indefinite" path="M 0 -34 A 34 34 0 1 1 -0.1 -34" />
        {/if}
        <!-- A small airliner, nose to the right, with Ziggy at the controls. -->
        <g transform="scale({0.7 * heading} 0.7) translate(-52 -24)">
          <path class="plane fin" d="M14 17 L6 1 L17 1 L30 17 Z" />
          <path class="plane wing far" d="M52 17 L62 6 L68 6 L64 17 Z" />
          <path class="plane body" d="M6 24 C6 19 11 17 20 17 L80 17 C93 17 102 20 102 24 C102 28 93 31 80 31 L20 31 C11 31 6 29 6 24 Z" />
          {#each [34, 42, 50, 58, 66] as x (x)}
            <circle class="window" cx={x} cy="22.5" r="1.8" />
          {/each}
          <path class="plane wing" d="M44 27 L62 27 L50 45 L41 45 Z" />
          <circle class="canopy" cx="88" cy="16" r="11" />
          <image href={ziggy} x="73" y="2" width="32" height="34" clip-path="url(#cockpit)" />
          <circle class="canopy-rim" cx="88" cy="16" r="11" />
        </g>
      </g>
    </g>
  </svg>
  </div>

  {#if unmapped.length > 0}
    <p class="muted note">Not on the map: {unmapped.map((r) => `${r.from}→${r.to}`).join(", ")}</p>
  {/if}
</section>

<style>
  .map { display: flex; flex-direction: column; gap: .5rem; min-height: 0; }
  .frame { flex: 1; min-height: 0; position: relative; overflow: hidden; background: #0e1020; }
  svg { position: absolute; inset: 0; display: block; }
  .graticule { fill: none; stroke: rgba(97, 105, 237, .14); stroke-width: 1; }
  .land { fill: #1d2140; stroke: rgba(127, 134, 241, .55); stroke-width: .8; }
  .borders { fill: none; stroke: rgba(127, 134, 241, .25); stroke-width: .6; }
  .leg { fill: none; stroke-width: 3; stroke-linecap: round; }
  .leg.dashed { stroke-dasharray: 8 10; }
  .leg.moving { animation: dash 1.2s linear infinite; }
  .leg.green { stroke: var(--green); }
  .leg.yellow { stroke: var(--yellow); }
  .leg.cyan { stroke: var(--cyan); }
  .leg.slate { stroke: var(--slate-500); }
  .leg.red { stroke: var(--red); }
  .airport circle { fill: var(--space-black); stroke: var(--indigo-200); stroke-width: 2; }
  .airport text, .hotel text {
    fill: var(--off-white); font: 600 18px var(--font-mono); text-anchor: middle;
  }
  .hotel rect { fill: var(--space-black); stroke-width: 2; }
  .hotel.green rect { stroke: var(--green); }
  .hotel.yellow rect, .hotel.cyan rect { stroke: var(--yellow); }
  .hotel.slate rect { stroke: var(--slate-500); }
  .hotel text { font-size: 12px; }
  .plane { stroke: #0b0b12; stroke-width: 1.4; stroke-linejoin: round; }
  .plane.body { fill: #e9ebff; }
  .plane.fin { fill: var(--uv-light); }
  .plane.wing { fill: var(--indigo-200); }
  .plane.wing.far { fill: var(--indigo-300); }
  .window { fill: var(--uv); }
  .canopy { fill: #1f203f; }
  .canopy-rim { fill: none; stroke: #0b0b12; stroke-width: 1.6; }
  .note { margin: 0; }
  @keyframes dash { to { stroke-dashoffset: -36; } }
  :global(.motion-paused) .leg.moving { animation-play-state: paused; }
</style>
