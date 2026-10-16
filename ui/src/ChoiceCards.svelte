<script lang="ts">
  import type { ToolPart } from "@temporalio/agent-harness-client";
  import { FARE_LABEL, HOTEL_TOOL, choiceRequest, hotelRequest, type Choice, type HotelChoice } from "./choices.ts";
  import { usd } from "./format.ts";

  let { part, answer }: { part: ToolPart; answer: (choice: Choice | HotelChoice) => Promise<unknown> } = $props();

  // Flights and hotels ask the same way, so they share these cards: a flight option is picked
  // at a fare, a hotel as a whole stay.
  const hotels = $derived(part.toolName === HOTEL_TOOL ? hotelRequest(part) : null);
  const flights = $derived(hotels ? null : choiceRequest(part));
  const question = $derived(hotels?.question ?? flights?.question ?? "");

  let sending = $state<{ id: string | null; fare: string | null } | null>(null);
  let comment = $state("");

  async function choose(id: string | null, fare: string | null = null) {
    sending = { id, fare };
    const note = id ? null : comment.trim() || null;
    try {
      await answer(hotels ? { hotel_id: id, comment: note } : { option_id: id, fare: fare as Choice["fare"], comment: note });
    } catch {
      sending = null;
    }
  }

  const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  const day = (date: string) => (/^\d{4}-\d{2}-\d{2}$/.test(date) ? DAY.format(new Date(`${date}T00:00:00Z`)) : date);
  const stops = (n: number) => (n === 0 ? "non-stop" : n === 1 ? "1 stop" : `${n} stops`);
  const nights = (from: string, to: string) => Math.max(1, Math.round((Date.parse(to) - Date.parse(from)) / 86_400_000));
</script>

<section class="choice" aria-label={question}>
  <header>
    <span class="badge progress">your choice</span>
    <h3 class="heading">{question}</h3>
  </header>

  <div class="options">
    {#if flights}
      {#each flights.options as option (option.option_id)}
        {@const chosen = sending?.id === option.option_id}
        <article class="card option" class:chosen class:dimmed={sending && !chosen}>
          <div class="about">
            <h4>{option.title}</h4>
            {#if option.note}<p class="muted note">{option.note}</p>{/if}
            <ul class="legs">
              {#each option.legs as leg (leg.flight_id)}
                <li>
                  <span class="route mono">{leg.origin} → {leg.destination}</span>
                  <span class="when">{day(leg.date)} · {leg.departure_time}–{leg.arrival_time}</span>
                  <span class="muted">{leg.airline} · {stops(leg.stops)}</span>
                </li>
              {/each}
            </ul>
          </div>
          <div class="fares" role="group" aria-label="Fares for {option.title}">
            {#each option.fares as fare (fare.level)}
              {@const thisOne = chosen && sending?.fare === fare.level}
              <button
                class="fare {fare.level}"
                class:picked={thisOne}
                disabled={sending !== null}
                aria-pressed={thisOne}
                onclick={() => choose(option.option_id, fare.level)}
              >
                <span class="level mono">{FARE_LABEL[fare.level] ?? fare.level}</span>
                <span class="price">{usd.format(fare.total_usd)}</span>
              </button>
            {/each}
          </div>
        </article>
      {/each}
    {:else if hotels}
      {@const stay = nights(hotels.check_in, hotels.check_out)}
      {#each hotels.options as hotel (hotel.hotel_id)}
        {@const chosen = sending?.id === hotel.hotel_id}
        <article class="card option" class:chosen class:dimmed={sending && !chosen}>
          <div class="about">
            <h4>{hotel.name} <span class="stars" aria-label="{hotel.star_rating} stars">{"★".repeat(hotel.star_rating)}</span></h4>
            {#if hotel.note}<p class="muted note">{hotel.note}</p>{/if}
            <ul class="legs">
              <li>
                <span class="route mono">{hotel.neighborhood}, {hotels.city}</span>
                <span class="when">{day(hotels.check_in)} – {day(hotels.check_out)} · {stay} {stay === 1 ? "night" : "nights"}</span>
                <span class="muted">{usd.format(hotel.price_per_night_usd)} a night</span>
              </li>
            </ul>
          </div>
          <div class="fares">
            <button
              class="fare stay"
              class:picked={chosen}
              disabled={sending !== null}
              aria-pressed={chosen}
              onclick={() => choose(hotel.hotel_id)}
            >
              <span class="level mono">Book stay</span>
              <span class="price">{usd.format(hotel.total_usd)}</span>
            </button>
          </div>
        </article>
      {/each}
    {/if}
  </div>

  {#if !sending}
    <form
      class="other"
      onsubmit={(event) => {
        event.preventDefault();
        void choose(null);
      }}
    >
      <label class="visually-hidden" for="choice-{part.toolId}">Something else</label>
      <input id="choice-{part.toolId}" placeholder="None of these? Say what you'd like instead" bind:value={comment} />
      <button class="button small secondary ultraviolet" type="submit">None of these</button>
    </form>
    <p class="muted">
      Monty's Workflow is waiting on your pick, durably: it holds until you choose, even across a
      worker restart.
    </p>
  {:else}
    <p class="muted">Sending your pick to Monty…</p>
  {/if}
</section>

<style>
  .choice { display: grid; gap: .6rem; min-width: 0; container-type: inline-size; }
  header { display: flex; align-items: center; gap: .7rem; }
  /* One option per row: what the trip is on the left, its fares stacked on the right. */
  .options { display: grid; gap: .7rem; }
  /* Each option reads as a card of its own: an ultraviolet edge, ringed in the brand gradient
     on hover, and in green once picked. */
  .option {
    display: grid; grid-template-columns: minmax(0, 1fr) 12.5rem; gap: .6rem 1.2rem;
    align-items: center; padding: 1rem 1.1rem 1rem 1.3rem;
    background: linear-gradient(to top right, #141414e6, #1f203fcc);
    box-shadow: inset 3px 0 0 var(--uv);
    transition: opacity .2s, border-color .2s, box-shadow .2s;
  }
  .option:hover:not(.dimmed) {
    border-image: linear-gradient(45deg, #444ce7, #b664ff) 1;
    box-shadow: inset 3px 0 0 var(--purple), 0 0 24px rgba(68, 76, 231, .25);
  }
  .option.chosen { border-image: var(--grad-green) 1; box-shadow: inset 3px 0 0 var(--green), 0 0 24px rgba(31, 241, 165, .2); }
  .option.dimmed { opacity: .45; }
  .about { display: grid; gap: .45rem; min-width: 0; }
  h4 { margin: 0; font-weight: 500; font-size: 1.05rem; color: var(--off-white); }
  .note { margin: 0; }
  .legs { list-style: none; margin: 0; padding: 0; display: grid; gap: .45rem; }
  .legs li { display: grid; gap: .1rem; font-size: .82rem; }
  .route { color: var(--indigo-100); font-size: .85rem; }
  .fares { display: grid; gap: .35rem; min-width: 0; }
  /* Too narrow for two columns: the fares sit under the legs, side by side. */
  @container (max-width: 26rem) {
    .option { grid-template-columns: minmax(0, 1fr); }
    .fares { grid-template-columns: repeat(auto-fit, minmax(5.5rem, 1fr)); }
  }
  /* Fares as the theme's gradient-ringed buttons, one gradient per cabin; hovering or picking
     one fills it. */
  .fare {
    --ring: linear-gradient(45deg, #1ff1a5, #c3ff62);
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: .1rem .8rem;
    padding: .5rem .7rem; cursor: pointer; text-align: left; font: inherit; color: var(--off-white);
    border: 2px solid transparent;
    background: linear-gradient(#141414, #141414) padding-box, var(--ring) border-box;
    transition: box-shadow .15s, color .15s, background .15s;
  }
  .fare.premium { --ring: linear-gradient(45deg, #444ce7, #b664ff); }
  .fare.business { --ring: linear-gradient(45deg, #b664ff, #ff6bff); }
  .fare.stay { --ring: linear-gradient(45deg, #444ce7, #b664ff); }
  .stars { color: var(--yellow); font-size: .8rem; letter-spacing: .05em; margin-left: .3rem; }
  .fare:hover:not(:disabled), .fare.picked {
    background: var(--ring) padding-box, var(--ring) border-box;
    box-shadow: 0 0 0 3px rgba(97, 105, 237, .45);
  }
  .fare.economy:hover:not(:disabled), .fare.economy.picked { color: var(--space-black); box-shadow: 0 0 0 3px rgba(31, 241, 165, .35); }
  .fare:hover:not(:disabled) .level, .fare.picked .level { color: inherit; }
  .fare:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--green-soft); }
  .fare:disabled { cursor: default; }
  .fare:disabled:not(.picked) { opacity: .6; }
  .level { font-size: .7rem; text-transform: uppercase; color: var(--indigo-100); }
  .price { font-variant-numeric: tabular-nums; font-weight: 500; }
  .other { display: flex; gap: .5rem; }
  .other { min-width: 0; }
  .other input {
    min-width: 0;
    flex: 1; padding: .45rem .6rem; font: inherit; color: var(--off-white);
    background: rgba(20, 20, 20, .9); border: 1px solid var(--border);
  }
  .other input:focus-visible { outline: none; border-color: var(--green); box-shadow: 0 0 0 2px var(--green-soft); }
  p { margin: 0; font-size: .78rem; }
</style>
