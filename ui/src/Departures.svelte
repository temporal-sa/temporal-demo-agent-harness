<script lang="ts">
  import type { TripBoard } from "./generated/MontyChatAgent.ts";
  import { usd } from "./format.ts";
  import SplitFlap from "./SplitFlap.svelte";
  import { isMoving, type Row, type Stage } from "./travel.ts";

  let {
    rows,
    board,
    away,
    still,
  }: { rows: Row[]; board: TripBoard | undefined; away: boolean; still: boolean } = $props();

  const STATUS: Record<Stage, { text: string; tone: string; meaning: string }> = {
    searching: { text: "SEARCHING", tone: "cyan", meaning: "Monty is searching" },
    options: { text: "OPTIONS", tone: "slate", meaning: "Searched; nothing booked yet" },
    clearance: { text: "CLEARANCE", tone: "yellow", meaning: "Waiting for your approval" },
    boarding: { text: "BOOKING", tone: "yellow", meaning: "Booking now" },
    confirmed: { text: "CONFIRMED", tone: "green", meaning: "Booked" },
    declined: { text: "CANCELLED", tone: "slate", meaning: "You declined it" },
    failed: { text: "FAILED", tone: "red", meaning: "The booking failed" },
  };

  // While a booking runs, its dots flip in one at a time and clear: "BOOKING." to
  // "BOOKING..." and back. Held at three when motion is paused or reduced.
  let dots = $state(3);
  const booking = $derived(!away && rows.some((row) => row.stage === "boarding"));
  $effect(() => {
    if (!booking || still) {
      dots = 3;
      return;
    }
    const timer = setInterval(() => (dots = (dots + 1) % 4), 700);
    return () => clearInterval(timer);
  });

  // Work that needs a worker reads as delayed while none answers; it resumes, not restarts.
  function status(row: Row) {
    if (away && isMoving(row.stage)) {
      return { text: "DELAYED", tone: "yellow", meaning: "No worker answering; resumes where it stopped" };
    }
    if (row.stage === "boarding") return { ...STATUS.boarding, text: "BOOKING" + ".".repeat(dots) };
    return STATUS[row.stage];
  }

  // Airline fare codes, as a boarding pass prints them: Y economy, W premium, J business.
  const FARE_CODES: Record<string, string> = { economy: "Y", premium: "W", business: "J" };

  function seatText(row: Row): string {
    if (row.kind !== "flight" || (!row.fare && !row.seat)) return "";
    return `${FARE_CODES[row.fare ?? "economy"] ?? "?"} ${row.seat ?? "--"}`;
  }

  const trip = $derived(board?.trips.at(-1));
  const remaining = $derived((trip?.remaining ?? []).filter((task) => !task.done));
  const total = $derived(rows.reduce((sum, row) => sum + (row.stage === "confirmed" ? (row.price ?? 0) : 0), 0));
</script>

<section class="card departures" aria-labelledby="departures-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="departures-title">Departures</h2>
    <span class="muted">{trip ? `${trip.description} · ${trip.traveler}` : "Agent state, streamed from the Workflow"}</span>
  </header>

  {#if rows.length === 0}
    <div class="empty">
      <SplitFlap text="NO DEPARTURES" width={13} {still} />
      <p class="muted">Tell Monty where you're going. Each search and booking lands here as it happens.</p>
    </div>
  {:else}
    <table>
      <thead>
        <tr class="eyebrow">
          <th scope="col">Flight</th>
          <th scope="col">Route</th>
          <th scope="col">Date</th>
          <th scope="col">Seat</th>
          <th scope="col">Status</th>
          <th scope="col">Conf</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.key)}
          {@const s = status(row)}
          <tr>
            <td><SplitFlap text={row.kind === "hotel" ? "HOTEL" : row.label || "------"} width={7} {still} /></td>
            <td>
              {#if row.kind === "flight"}
                <SplitFlap text="{row.from} {row.to}" width={7} {still} />
              {:else}
                <SplitFlap text={row.from || row.label} width={10} {still} />
              {/if}
            </td>
            <td>
              <SplitFlap text={row.date.slice(5) || ""} width={5} {still} />
              {#if row.moreDates > 0}<span class="more mono" title="{row.moreDates} more dates searched">+{row.moreDates}</span>{/if}
            </td>
            <td class="seat" title={row.fare ? `${row.fare}${row.seat ? `, seat ${row.seat}` : ""}` : ""}>
              <SplitFlap text={seatText(row)} width={5} {still} />
            </td>
            <td class="status {s.tone}" title={s.meaning}><SplitFlap text={s.text} width={10} {still} /></td>
            <td class="code"><SplitFlap text={row.code} width={10} {still} /></td>
          </tr>
          {#if row.kind === "hotel" && row.label && row.from}
            <tr class="detail"><td></td><td colspan="5" class="muted">{row.label}</td></tr>
          {/if}
        {/each}
      </tbody>
    </table>

    <footer class="summary">
      {#if remaining.length > 0}
        <p class="muted">
          Still to do:
          {#each remaining as task, i (task.text)}<span class="todo">{task.text}</span>{i < remaining.length - 1 ? " · " : ""}{/each}
        </p>
      {:else if trip}
        <p class="muted">Nothing left to do on this trip.</p>
      {/if}
      {#if total > 0}
        <p class="total mono">Total <span>{usd.format(total)}</span></p>
      {/if}
    </footer>
  {/if}
</section>

<style>
  .departures { display: flex; flex-direction: column; gap: .8rem; min-height: 0; overflow: auto; }
  .empty { margin: auto; display: grid; justify-items: center; gap: .8rem; text-align: center; font-size: 1.2rem; }
  .empty p { font-size: .8rem; max-width: 22rem; margin: 0; }
  table { border-collapse: separate; border-spacing: 0 .35rem; font-size: .82rem; }
  th { text-align: left; font-weight: 500; padding: 0 .6rem .2rem 0; }
  td { padding: 0 .6rem 0 0; color: var(--yellow); vertical-align: middle; white-space: nowrap; }
  td.status.green { color: var(--green); }
  td.status.yellow { color: var(--yellow); }
  td.status.cyan { color: var(--cyan); }
  td.status.slate { color: var(--slate-300); }
  td.status.red { color: var(--red); }
  td.code, td.seat { color: var(--off-white); }
  .more { margin-left: .3rem; font-size: .75rem; color: var(--indigo-100); }
  tr.detail td { font-size: .75rem; padding-top: 0; }
  .summary { display: flex; justify-content: space-between; gap: 1rem; align-items: baseline; margin-top: auto; }
  .summary p { margin: 0; }
  .todo { color: var(--indigo-100); }
  .total { color: var(--slate-300); font-size: .8rem; white-space: nowrap; }
  .total span { color: var(--off-white); font-size: 1.1rem; margin-left: .4rem; }
</style>
