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

/** Splits `**bold**` out of model text, the only markdown Monty's replies lean on. */
export function emphasis(text: string): { text: string; bold: boolean }[] {
  return text.split(/\*\*(.+?)\*\*/g).map((segment, i) => ({ text: segment, bold: i % 2 === 1 }));
}

export const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
