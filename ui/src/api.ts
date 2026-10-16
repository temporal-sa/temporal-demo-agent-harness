import { HttpTransport, startSession, type SessionSummary } from "@temporalio/agent-harness-client";
import { MontyChatAgent, type TravelerContext } from "./generated/MontyChatAgent.ts";

/** One transport for the page, against the same `api/` the console uses. */
export const transport = new HttpTransport();

/** What `GET api/view` returns: everything the page needs on load, in one request. */
export interface PageView {
  /** Every session this person may name starts with this. */
  session_prefix: string;
  /** This namespace in the Temporal UI. */
  temporal_ui_url: string;
  sessions: SessionSummary[];
}

export async function loadView(): Promise<PageView> {
  const response = await fetch("api/view");
  if (!response.ok) throw new Error(`Couldn't load the demo (${response.status})`);
  return response.json();
}

/** A new session ID inside the caller's prefix, chosen here so the page needn't wait for it. */
export function newSessionId(prefix: string): string {
  const bytes = crypto.getRandomValues(new Uint8Array(6));
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

/** The traveler's local date and time zone, so Monty plans from today rather than from
 *  whenever its model was trained. */
export function travelerContext(now = new Date()): TravelerContext {
  const pad = (n: number) => String(n).padStart(2, "0");
  return {
    today: `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
  };
}

export function createTrip(sessionId: string): Promise<SessionSummary> {
  return startSession(transport, MontyChatAgent, { sessionId, data: travelerContext() });
}
