<script lang="ts">
  import type { ToolPart } from "@temporalio/agent-harness-client";
  import { usd } from "./format.ts";

  type Fare = "economy" | "premium" | "business";
  interface Leg {
    flight_id: string;
    origin: string;
    destination: string;
    date: string;
    airline: string;
    departure_time: string;
    arrival_time: string;
    stops: number;
  }
  interface Option {
    option_id: string;
    title: string;
    legs: Leg[];
    fares: { level: Fare; total_usd: number }[];
    note?: string | null;
  }
  export interface Choice {
    option_id: string | null;
    fare: Fare | null;
    comment: string | null;
  }

  let { part, answer }: { part: ToolPart; answer: (choice: Choice) => Promise<unknown> } = $props();

  const request = $derived(
    ((part.input as { request?: { question: string; options: Option[] } }).request ?? {
      question: "",
      options: [],
    }) as { question: string; options: Option[] },
  );
  const waiting = $derived(part.state === "awaiting_callback");

  // Once answered, the choice comes back on the tool's output, as Python prints the model.
  const answered = $derived.by((): Choice | null => {
    if (!part.output) return null;
    const field = (name: string) => new RegExp(`${name}='([^']*)'`).exec(part.output ?? "")?.[1] ?? null;
    return { option_id: field("option_id"), fare: field("fare") as Fare | null, comment: field("comment") };
  });

  let sending = $state<Choice | null>(null);
  let comment = $state("");
  const picked = $derived(sending ?? answered);

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
  const FARE_LABEL: Record<Fare, string> = { economy: "Economy", premium: "Premium", business: "Business" };
</script>

<section class="choice" aria-label={request.question}>
  <header>
    <span class="badge {waiting ? 'progress' : 'good'}">{waiting ? "your choice" : "chosen"}</span>
    <h3 class="heading">{request.question}</h3>
  </header>

  <div class="options">
    {#each request.options as option (option.option_id)}
      {@const chosen = picked?.option_id === option.option_id}
      <article class="card option" class:chosen class:dimmed={picked && !chosen}>
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
            {@const thisOne = chosen && picked?.fare === fare.level}
            <button
              class="fare"
              class:picked={thisOne}
              disabled={!waiting || sending !== null}
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

  {#if waiting && !sending}
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
  {:else if picked && picked.option_id === null}
    <p class="muted">You asked for something else{picked.comment ? `: “${picked.comment}”` : "."}</p>
  {/if}
</section>

<style>
  .choice { display: grid; gap: .6rem; min-width: 0; }
  header { display: flex; align-items: center; gap: .7rem; }
  .options { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(15rem, 100%), 1fr)); gap: .6rem; }
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
