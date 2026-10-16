<script lang="ts">
  import { geoGraticule10, geoMercator, geoPath, type GeoProjection } from "d3-geo";
  import type { FeatureCollection, MultiLineString } from "geojson";
  import { AIRPORTS } from "./airports.ts";
  import { isMoving, type Row, type Stage } from "./travel.ts";

  let { rows, away }: { rows: Row[]; away: boolean } = $props();

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

  /** The ends and control point of the shallow arc from one airport to another, bowed to
   *  the left of travel. */
  function curve(from: string, to: string) {
    const [x1, y1] = point(from);
    const [x2, y2] = point(to);
    const bow = 0.22;
    return { x1, y1, x2, y2, cx: (x1 + x2) / 2 + (y2 - y1) * bow, cy: (y1 + y2) / 2 - (x2 - x1) * bow };
  }

  function arc(from: string, to: string): string {
    const { x1, y1, x2, y2, cx, cy } = curve(from, to);
    return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
  }

  const TONE: Record<Stage, string> = {
    searching: "cyan", options: "slate", clearance: "yellow", boarding: "yellow",
    confirmed: "green", declined: "slate", failed: "red",
  };

  // The caption says which leg Monty is working on, from the same rows as the board.
  const active = $derived(flights.findLast((r) => ["searching", "boarding", "clearance"].includes(r.stage)));
  const landed = $derived(flights.findLast((r) => r.stage === "confirmed"));
  const caption = $derived(
    away && rows.some((r) => isMoving(r.stage))
      ? "Delayed · no worker answering"
      : active?.stage === "clearance"
        ? `Waiting for your approval · ${active.from} → ${active.to}`
        : active
          ? `${active.stage === "searching" ? "Searching" : "Booking"} ${active.from} → ${active.to}`
          : landed
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

</script>

<section class="card map" aria-labelledby="map-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="map-title">Route map</h2>
    <span class="muted">{caption}</span>
  </header>

  <div class="frame" bind:clientWidth={width} bind:clientHeight={height}>
  <svg viewBox="0 0 {W} {H}" width={W} height={H} role="img" aria-label="Route map. {caption}.">
    <defs>
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
  .note { margin: 0; }
  @keyframes dash { to { stroke-dashoffset: -36; } }
  :global(.motion-paused) .leg.moving { animation-play-state: paused; }
</style>
