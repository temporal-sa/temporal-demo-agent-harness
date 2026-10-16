import type { ToolState } from "@temporalio/agent-harness-client";

/** `book_flight` → `Book flight`. */
export function toolLabel(name: string): string {
  if (name === "run_travel_code") return "Run a travel script";
  const words = name.replace(/^monty_/, "").replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** The badge for a tool call: yellow while it waits or runs, green when done, red only on failure. */
export function toolBadge(state: ToolState): { label: string; tone: "progress" | "good" | "idle" | "error" } {
  switch (state) {
    case "requested":
    case "evaluating":
      return { label: "requested", tone: "progress" };
    case "awaiting_approval":
      return { label: "needs approval", tone: "progress" };
    case "awaiting_callback":
      return { label: "waiting", tone: "progress" };
    case "approved":
      return { label: "approved", tone: "good" };
    case "running":
      return { label: "running", tone: "progress" };
    case "done":
      return { label: "done", tone: "good" };
    case "denied":
      return { label: "declined", tone: "idle" };
    case "failed":
      return { label: "failed", tone: "error" };
  }
}

export const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export type Policy = "allow_safe" | "strict" | "dangerously_skip_all";

/** What Monty asks about before any `set_approval_policy`: everything but its own trip board. */
export const DEFAULT_POLICY_HINT = "Monty asks before each script, search, and booking.";

/** What each policy `set_approval_policy` accepts asks a person to approve. */
export const POLICIES: { value: Policy; label: string; hint: string }[] = [
  { value: "strict", label: "Ask for everything", hint: "Every tool call waits for you, trip board included." },
  { value: "allow_safe", label: "Trust scripts", hint: "Scripts and the trip board run; searches and bookings still ask." },
  { value: "dangerously_skip_all", label: "Never ask", hint: "Every tool call runs without approval." },
];

export function policyLabel(policy: Policy): string {
  return POLICIES.find((p) => p.value === policy)?.label ?? policy;
}

export type Model = "gemini-3.8-flash" | "gemini-3.1-flash-lite";

/** The models `set_model` accepts; the first is the agent's default. */
export const MODELS: Model[] = ["gemini-3.8-flash", "gemini-3.1-flash-lite"];

/** A one-line summary of a tool call's arguments, for a list of many at once. */
export function callSummary(toolName: string, input: Record<string, unknown>): string {
  const req = (input.request ?? input) as Record<string, string>;
  switch (toolName) {
    case "search_flights":
      return `${req.origin} → ${req.destination} · ${req.date}`;
    case "search_hotels":
      return `${req.city} · ${req.check_in} → ${req.check_out}`;
    case "get_seat_map":
      return req.flight_id;
    case "book_flight":
      return [req.flight_id, req.fare ?? "economy", req.seat ?? "any seat", req.passenger_name].join(" · ");
    case "book_hotel":
      return `${req.hotel_id} · ${req.guest_name}`;
    default: {
      const text = JSON.stringify(req);
      return text.length > 90 ? `${text.slice(0, 87)}…` : text;
    }
  }
}
