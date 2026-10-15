<script lang="ts">
  import { createHarnessContext } from "@temporalio/agent-harness-svelte";
  import { createTrip, loadView, newSessionId, type PageView } from "./api.ts";
  import logo from "./assets/temporal-logo.svg";
  import { motion, toggleMotion } from "./motion.svelte.ts";
  import Trip from "./Trip.svelte";

  createHarnessContext();

  let view = $state<PageView | null>(null);
  let loadError = $state<string | null>(null);
  // The session the page shows, and the one it is creating (null once created).
  let sessionId = $state<string | null>(null);
  let creating = $state<string | null>(null);

  function show(id: string) {
    const url = new URL(location.href);
    url.searchParams.set("s", id);
    history.replaceState(null, "", url);
    sessionId = id;
  }

  function newTrip() {
    if (!view) return;
    // The page names the session and switches to it immediately; the trip opens once
    // Temporal has started the Workflow, usually before anyone has finished typing.
    const id = newSessionId(view.session_prefix);
    creating = id;
    sessionId = null;
    createTrip(id).then(
      () => {
        if (creating === id) {
          creating = null;
          show(id);
        }
      },
      (error: Error) => {
        creating = null;
        loadError = `Couldn't start a trip: ${error.message}`;
      },
    );
  }

  loadView().then(
    (loaded) => {
      view = loaded;
      const requested = new URL(location.href).searchParams.get("s");
      const latest = loaded.sessions
        .filter((s) => !s.closed)
        .sort((a, b) => b.created_at - a.created_at)[0];
      if (requested?.startsWith(loaded.session_prefix)) show(requested);
      else if (latest) show(latest.workflow_id);
      else newTrip();
    },
    (error: Error) => (loadError = error.message),
  );

  const workflowLink = $derived(
    view && sessionId ? `${view.temporal_ui_url}/workflows/${encodeURIComponent(sessionId)}` : null,
  );
  const consoleLink = $derived(sessionId ? `console/?s=${encodeURIComponent(sessionId)}` : "console/");
</script>

<div class="app" class:motion-paused={motion.paused}>
  <header class="topbar">
    <div class="brand">
      <img src={logo} alt="Temporal" width="132" height="34" />
      <div>
        <p class="eyebrow">Agent Harness · Code Mode · Human in the loop</p>
        <h1 class="title">Monty, a <span class="text-gradient-ultraviolet">durable</span> travel agent</h1>
      </div>
    </div>
    <nav class="links" aria-label="Views">
      {#if workflowLink}
        <a class="button small secondary ultraviolet" href={workflowLink} target="_blank" rel="noreferrer">Temporal UI ↗</a>
      {/if}
      <a class="button small secondary ultraviolet" href={consoleLink}>Harness console</a>
      {#if !motion.reduced}
        <button class="button small secondary ultraviolet" aria-pressed={motion.paused} onclick={toggleMotion}>
          {motion.paused ? "Play motion" : "Pause motion"}
        </button>
      {/if}
      <button class="button small primary ultraviolet" onclick={newTrip} disabled={!view || creating !== null}>
        New trip
      </button>
    </nav>
  </header>

  {#if loadError}
    <div class="card failure" role="alert"><span class="badge error">error</span> {loadError}</div>
  {/if}

  {#if sessionId}
    {#key sessionId}
      <Trip {sessionId} />
    {/key}
  {:else if !loadError}
    <div class="card starting" role="status">
      <p class="heading">{creating ? "Starting a new trip…" : "Loading your trips…"}</p>
      <p class="muted">
        {creating ? "Temporal is starting the agent Workflow that will hold this conversation." : ""}
      </p>
    </div>
  {/if}
</div>
