<script lang="ts">
  import type { TripBoard } from "./generated/MontyChatAgent.ts";
  import { usd } from "./format.ts";

  let { board }: { board: TripBoard | undefined } = $props();

  const statusTone = { collecting: "progress", booked: "good", cancelled: "idle" } as const;
</script>

<section class="card board" aria-labelledby="board-title">
  <header class="panel-head">
    <h2 class="eyebrow" id="board-title">Trip board</h2>
    <span class="muted">Agent state, streamed from the Workflow</span>
  </header>

  {#if !board || board.trips.length === 0}
    <div class="empty">
      <p class="heading">No trip yet.</p>
      <p class="muted">Tell Monty where you're going. Each booking lands here as it happens.</p>
    </div>
  {:else}
    <div class="trips">
      {#each board.trips as trip (trip.trip_id)}
        {@const bookings = [...(trip.flights ?? []), ...(trip.hotels ?? [])]}
        {@const total = bookings.reduce((sum, b) => sum + (b.price_usd ?? 0), 0)}
        <article class="trip">
          <header class="trip-head">
            <div>
              <h3 class="heading">{trip.description}</h3>
              <p class="muted mono">{trip.traveler} · {trip.trip_id}</p>
            </div>
            <span class="badge {statusTone[trip.status ?? 'collecting']}">{trip.status ?? "collecting"}</span>
          </header>

          {#if bookings.length > 0}
            <ul class="bookings">
              {#each bookings as booking (booking.confirmation_code)}
                <li class="booking">
                  <span class="kind mono">{booking.kind}</span>
                  <span class="detail">{booking.detail}</span>
                  <span class="code mono">{booking.confirmation_code}</span>
                  <span class="price mono">{usd.format(booking.price_usd ?? 0)}</span>
                </li>
              {/each}
            </ul>
            <p class="total mono">Total <span>{usd.format(total)}</span></p>
          {/if}

          {#if (trip.remaining ?? []).length > 0}
            <ul class="checklist">
              {#each trip.remaining ?? [] as task (task.text)}
                <li class:done={task.done}>
                  <span class="tick" aria-hidden="true">{task.done ? "✓" : ""}</span>
                  <span>{task.text}</span>
                  <span class="visually-hidden">{task.done ? "done" : "to do"}</span>
                </li>
              {/each}
            </ul>
          {/if}
        </article>
      {/each}
    </div>
  {/if}
</section>

<style>
  .board { display: flex; flex-direction: column; gap: 1rem; overflow: auto; }
  .empty { margin: auto; text-align: center; max-width: 22rem; display: grid; gap: .5rem; }
  .trips { display: grid; gap: 1rem; }
  .trip { border: 1px solid var(--border); padding: 1rem; display: grid; gap: .9rem; }
  .trip-head { display: flex; justify-content: space-between; align-items: start; gap: 1rem; }
  .trip-head p { margin: .25rem 0 0; }
  .bookings { list-style: none; margin: 0; padding: 0; display: grid; gap: .4rem; }
  .booking {
    display: grid; grid-template-columns: 4.5rem 1fr auto auto; gap: .75rem; align-items: baseline;
    padding: .55rem .7rem; background: rgba(68, 76, 231, .12); border-left: 2px solid var(--green);
    animation: land .4s ease-out;
  }
  .kind { text-transform: uppercase; font-size: .7rem; color: var(--indigo-100); }
  .code { color: var(--green); font-size: .8rem; }
  .price { font-variant-numeric: tabular-nums; }
  .total { margin: 0; text-align: right; color: var(--slate-300); font-size: .8rem; }
  .total span { color: var(--off-white); font-size: 1rem; margin-left: .5rem; }
  .checklist { list-style: none; margin: 0; padding: 0; display: grid; gap: .35rem; }
  .checklist li { display: flex; gap: .6rem; align-items: center; }
  .checklist li.done { color: var(--slate-300); text-decoration: line-through; }
  .tick {
    width: 1.1rem; height: 1.1rem; border: 1px solid var(--slate-500); display: inline-grid;
    place-items: center; font-size: .75rem; color: var(--space-black); flex: none;
  }
  .done .tick { background: var(--green); border-color: var(--green); }
  @keyframes land { from { opacity: 0; transform: translateY(-4px); } }
</style>
