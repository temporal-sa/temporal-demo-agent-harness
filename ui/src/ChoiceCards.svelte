<script lang="ts">
  import type { ToolPart } from "@temporalio/agent-harness-client";
  import { FARE_LABEL, choiceRequest, type Choice } from "./choices.ts";
  import { usd } from "./format.ts";

  let { part, answer }: { part: ToolPart; answer: (choice: Choice) => Promise<unknown> } = $props();

  const request = $derived(choiceRequest(part));
  let sending = $state<Choice | null>(null);
  let comment = $state("");

  async function choose(choice: Choice) {
    sending = choice;
    try {
      await answer(choice);
    } catch {
      sending = null;
    }
  }

  const DAY = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  const day = (date: string) => (/^\d{4}-\d{2}-\d{2}$/.test(date) ? DAY.format(new Date(`${date}T00:00:00Z`)) : date);
  const stops = (n: number) => (n === 0 ? "non-stop" : n === 1 ? "1 stop" : `${n} stops`);
</script>

<section class="choice" aria-label={request.question}>
  <header>
    <span class="badge progress">your choice</span>
    <h3 class="heading">{request.question}</h3>
  </header>

  <div class="options">
    {#each request.options as option (option.option_id)}
      {@const chosen = sending?.option_id === option.option_id}
      <article class="card option" class:chosen class:dimmed={sending && !chosen}>
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
        <div class="fares" role="group" aria-label="Fares for {option.title}">
          {#each option.fares as fare (fare.level)}
            {@const thisOne = chosen && sending?.fare === fare.level}
            <button
              class="fare"
              class:picked={thisOne}
              disabled={sending !== null}
              aria-pressed={thisOne}
              onclick={() => choose({ option_id: option.option_id, fare: fare.level, comment: null })}
            >
              <span class="level mono">{FARE_LABEL[fare.level] ?? fare.level}</span>
              <span class="price">{usd.format(fare.total_usd)}</span>
            </button>
          {/each}
        </div>
      </article>
    {/each}
  </div>

  {#if !sending}
    <form
      class="other"
      onsubmit={(event) => {
        event.preventDefault();
        void choose({ option_id: null, fare: null, comment: comment.trim() || null });
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
  .choice { display: grid; gap: .6rem; min-width: 0; }
  header { display: flex; align-items: center; gap: .7rem; }
  .options { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(16rem, 100%), 1fr)); gap: .8rem; }
  .option { display: grid; gap: .5rem; align-content: start; transition: opacity .2s, border-color .2s; }
  .option.chosen { border-color: var(--green); }
  .option.dimmed { opacity: .55; }
  h4 { margin: 0; font-weight: 500; font-size: .95rem; color: var(--off-white); }
  .note { margin: 0; }
  .legs { list-style: none; margin: 0; padding: 0; display: grid; gap: .45rem; }
  .legs li { display: grid; gap: .1rem; font-size: .82rem; }
  .route { color: var(--indigo-100); font-size: .85rem; }
  .fares { display: grid; grid-template-columns: repeat(auto-fit, minmax(5.5rem, 1fr)); gap: .35rem; min-width: 0; }
  .fare {
    display: grid; gap: .1rem; padding: .45rem .5rem; cursor: pointer; text-align: left;
    background: var(--space-black); color: var(--off-white); border: 1px solid var(--uv-light);
    font: inherit;
  }
  .fare:hover:not(:disabled) { border-color: var(--green); background: rgba(31, 241, 165, .08); }
  .fare:focus-visible { outline: none; box-shadow: 0 0 0 2px var(--green-soft); }
  .fare:disabled { cursor: default; }
  .fare.picked { border-color: var(--green); background: rgba(31, 241, 165, .15); }
  .level { font-size: .7rem; text-transform: uppercase; color: var(--indigo-100); }
  .price { font-variant-numeric: tabular-nums; }
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
