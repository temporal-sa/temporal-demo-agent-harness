<script lang="ts">
  import { DEFAULT_POLICY_HINT, MODELS, POLICIES, type Model, type Policy } from "./format.ts";

  let {
    model,
    policy,
    setModel,
    setPolicy,
  }: {
    model: Model;
    /** null until a policy has been chosen in this session. */
    policy: Policy | null;
    setModel: (model: Model) => void;
    setPolicy: (policy: Policy) => void;
  } = $props();

  const hint = $derived(policy ? POLICIES.find((p) => p.value === policy)?.hint : DEFAULT_POLICY_HINT);
</script>

<div class="settings" role="group" aria-label="Agent settings">
  <label>
    <span class="eyebrow">Model</span>
    <select value={model} onchange={(event) => setModel(event.currentTarget.value as Model)}>
      {#each MODELS as option (option)}
        <option value={option}>{option}</option>
      {/each}
    </select>
  </label>
  <label>
    <span class="eyebrow">Approvals</span>
    <select value={policy ?? ""} onchange={(event) => setPolicy(event.currentTarget.value as Policy)}>
      {#if !policy}
        <option value="" disabled>Ask before travel calls</option>
      {/if}
      {#each POLICIES as option (option.value)}
        <option value={option.value}>{option.label}</option>
      {/each}
    </select>
  </label>
  <p class="muted">{hint} Changes apply right away, even mid-turn.</p>
</div>

<style>
  .settings { display: flex; flex-wrap: wrap; gap: .5rem 1rem; align-items: end; }
  label { display: grid; gap: .25rem; }
  select {
    font: 500 .8rem var(--font-mono); color: var(--off-white); background: var(--space-black);
    border: 1px solid var(--border); padding: .35rem .5rem;
  }
  select:focus-visible { outline: none; border-color: var(--green); box-shadow: 0 0 0 2px var(--green-soft); }
  p { margin: 0; flex: 1 1 14rem; }
</style>
