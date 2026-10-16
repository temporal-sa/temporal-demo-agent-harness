import type { AgentView, ToolPart } from "@temporalio/agent-harness-client";
import type { TripBoard } from "./generated/ZiggyChatAgent.ts";

/** Where one flight or hotel stands, from its first search to its confirmation. */
export type Stage = "searching" | "options" | "clearance" | "boarding" | "confirmed" | "declined" | "failed";

/** A row on the departures board: one flight leg or one hotel stay. */
export interface Row {
  key: string;
  kind: "flight" | "hotel";
  stage: Stage;
  /** Flight: origin and destination codes. Hotel: the city, twice. */
  from: string;
  to: string;
  /** The first date searched or booked for this row. */
  date: string;
  /** How many other dates were searched on this route, shown as "+N". */
  moreDates: number;
  /** Flight number or hotel name, once known. */
  label: string;
  /** A flight's fare level and seat, once chosen. */
  fare: string | null;
  seat: string | null;
  code: string;
  price: number | null;
}

const RANK: Record<Stage, number> = {
  declined: 0, failed: 1, options: 2, searching: 3, clearance: 4, boarding: 5, confirmed: 6,
};

/** Two-letter codes for the airlines Ziggy's simulated backend books, as a departure board
 *  would show them. Anything else shows its first two letters. */
const AIRLINE_CODES: Record<string, string> = {
  "American": "AA", "American Airlines": "AA", "Alaska": "AS", "Delta": "DL", "Delta Air Lines": "DL", "United": "UA",
  "United Airlines": "UA", "JetBlue": "B6", "Southwest": "WN", "Southwest Airlines": "WN",
  "Alaska Airlines": "AS", "Spirit": "NK", "Frontier": "F9", "Lufthansa": "LH",
  "British Airways": "BA", "Air France": "AF", "Swiss": "LX", "Emirates": "EK",
};

/** The code for the airline named anywhere in a booking's detail ("Delta FL-... 13:30"). */
function airlineCode(detail: string): string {
  const known = Object.keys(AIRLINE_CODES)
    .filter((name) => detail.includes(name))
    .sort((a, b) => b.length - a.length)[0];
  return known ? AIRLINE_CODES[known] : detail.replace(/[^A-Za-z]/g, "").slice(0, 2).toUpperCase();
}

/** `FL-SFOJFK-20261103-003` → origin, destination, date, and number, the shape Ziggy's
 *  simulated backend issues. IDs from before dates were added, `FL-SFOJFK-003`, have no date. */
const FLIGHT_ID = /FL-([A-Z]{3})([A-Z]{3})-(?:(\d{4})(\d{2})(\d{2})-)?(\d+)/;

function parseFlightId(id: string): { from: string; to: string; date: string; number: string } | null {
  const m = FLIGHT_ID.exec(id);
  if (!m) return null;
  return { from: m[1], to: m[2], date: m[3] ? `${m[3]}-${m[4]}-${m[5]}` : "", number: m[6] };
}

/** A host call's arguments arrive as `{request: {...}}`. */
function request(part: ToolPart): Record<string, string> {
  const input = part.input as Record<string, unknown>;
  return ((input.request ?? input) as Record<string, string>) ?? {};
}

/** The confirmation code in a finished booking call's output, which prints the response
 *  Python-style (`confirmation_code='AIR-…'`) or as JSON. */
function confirmationCode(part: ToolPart): string {
  if (part.state !== "done" || !part.output) return "";
  return /confirmation_code['"]?\s*[:=]\s*['"]([^'"]+)['"]/.exec(part.output)?.[1] ?? "";
}

function stageOf(part: ToolPart, kind: "search" | "book"): Stage {
  switch (part.state) {
    case "awaiting_approval":
    case "evaluating":
      return "clearance";
    case "denied":
      return "declined";
    case "failed":
      return "failed";
    case "done":
      return kind === "search" ? "options" : "confirmed";
    default:
      return kind === "search" ? "searching" : "boarding";
  }
}

/**
 * The board's rows, built from two sources: the agent's tool calls, which show work in
 * progress, and its trip board state, which is the record of what was actually booked.
 */
export function departures(agents: readonly AgentView[], board: TripBoard | undefined): Row[] {
  const rows = new Map<string, Row>();
  const hotelCities = new Map<string, string>();

  // Every date searched on a route, so a broad search reads as one row with "+N" more.
  const searchedDates = new Map<string, Set<string>>();

  function upsert(row: Omit<Row, "moreDates">) {
    const existing = rows.get(row.key);
    if (!existing) return void rows.set(row.key, { ...row, moreDates: 0 });
    rows.set(row.key, {
      ...existing,
      stage: RANK[row.stage] >= RANK[existing.stage] ? row.stage : existing.stage,
      date: existing.date || row.date,
      label: row.label || existing.label,
      code: row.code || existing.code,
      price: row.price ?? existing.price,
      fare: row.fare ?? existing.fare,
      seat: row.seat ?? existing.seat,
    });
  }

  const tools = agents.flatMap((agent) =>
    agent.messages.flatMap((message) => message.parts.filter((p): p is ToolPart => p.type === "tool")),
  );
  for (const part of tools) {
    const req = request(part);
    if (part.toolName === "search_flights" && req.origin && req.destination) {
      const route = `${req.origin}-${req.destination}`;
      if (req.date) searchedDates.set(route, (searchedDates.get(route) ?? new Set()).add(req.date));
      upsert({
        key: `search:${route}`, kind: "flight", stage: stageOf(part, "search"),
        from: req.origin, to: req.destination, date: "", label: "", code: "", price: null,
        fare: null, seat: null,
      });
    } else if (part.toolName === "book_flight" && req.flight_id) {
      const flight = parseFlightId(req.flight_id);
      if (!flight) continue;
      upsert({
        key: `flight:${req.flight_id}`, kind: "flight", stage: stageOf(part, "book"),
        from: flight.from, to: flight.to, date: flight.date, label: `FL ${flight.number}`,
        code: confirmationCode(part), price: null, fare: req.fare ?? "economy", seat: null,
      });
    } else if (part.toolName === "select_seat" && req.flight_id && part.state === "done") {
      // A seat chosen after booking lands on the flight's row once the airline confirms it.
      const row = rows.get(`flight:${req.flight_id}`);
      if (row) rows.set(row.key, { ...row, seat: req.seat });
    } else if (part.toolName === "search_hotels" && req.city) {
      const prefix = req.city.slice(0, 3).toUpperCase();
      hotelCities.set(prefix, req.city);
      upsert({
        key: `hotel:${prefix}`, kind: "hotel", stage: stageOf(part, "search"),
        from: req.city, to: req.city, date: req.check_in ?? "", label: "", code: "", price: null,
        fare: null, seat: null,
      });
    } else if (part.toolName === "book_hotel" && req.hotel_id) {
      const prefix = req.hotel_id.split("-")[1] ?? "";
      const city = hotelCities.get(prefix) ?? prefix;
      upsert({
        key: `hotel:${prefix}`, kind: "hotel", stage: stageOf(part, "book"),
        from: city, to: city, date: "", label: "", code: confirmationCode(part), price: null,
        fare: null, seat: null,
      });
    }
  }

  // A board record finds the row its booking call made by confirmation code, which every
  // record carries, rather than by the ID Ziggy may or may not have written into its detail.
  const byCode = (code: string) => [...rows.values()].find((row) => row.code && row.code === code);

  // The trip board is the record: its bookings are confirmed whatever the tool calls say.
  for (const trip of board?.trips ?? []) {
    for (const booked of trip.flights ?? []) {
      const id = FLIGHT_ID.exec(booked.detail)?.[0];
      const flight = id ? parseFlightId(id) : null;
      const made = byCode(booked.confirmation_code);
      const number = flight?.number ?? made?.label.split(" ")[1];
      upsert({
        key: made?.key ?? (id ? `flight:${id}` : `flight:${booked.confirmation_code}`),
        kind: "flight", stage: "confirmed", from: flight?.from ?? "", to: flight?.to ?? "",
        date: flight?.date ?? "",
        label: number ? `${airlineCode(booked.detail)} ${number}` : booked.detail,
        code: booked.confirmation_code, price: booked.price_usd ?? null,
        fare: booked.fare ?? null, seat: booked.seat ?? null,
      });
    }
    for (const hotel of trip.hotels ?? []) {
      const prefix = /HT-([A-Z]{3})-\d+/.exec(hotel.detail)?.[1];
      const known = prefix && rows.has(`hotel:${prefix}`);
      upsert({
        key: byCode(hotel.confirmation_code)?.key ?? (known ? `hotel:${prefix}` : `hotel:${hotel.confirmation_code}`),
        kind: "hotel", stage: "confirmed", from: "", to: "", date: "",
        label: hotel.detail, code: hotel.confirmation_code, price: hotel.price_usd ?? null,
        fare: null, seat: null,
      });
    }
  }
  // A route's search row gives way to its bookings, which take its date when only one was
  // searched. Otherwise it shows the first date searched and how many more.
  // Once a flight is booked, the searches it settled go too: any searched route that shares
  // its origin or destination (ATL→GVA once ATL→ZRH is booked), and every unbooked search
  // once the trip itself is booked.
  const bookings = [...rows.values()].filter((r) => r.key.startsWith("flight:") && r.stage !== "declined");
  const tripBooked = (board?.trips ?? []).some((trip) => trip.status === "booked");
  const settled = (row: Row) =>
    tripBooked ||
    bookings.some((b) => b.from === row.from || b.to === row.to);
  for (const [key, row] of rows) {
    const route = `${row.from}-${row.to}`;
    const dates = [...(searchedDates.get(route) ?? [])].sort();
    if (key.startsWith("search:")) {
      if (settled(row) && !isMoving(row.stage) && row.stage !== "clearance") rows.delete(key);
      else rows.set(key, { ...row, date: dates[0] ?? "", moreDates: Math.max(dates.length - 1, 0) });
    } else if (key.startsWith("flight:") && !row.date && dates.length === 1) {
      rows.set(key, { ...row, date: dates[0] });
    }
  }

  // By date, like a real board; a flight sorts ahead of the stay that starts the same day.
  return [...rows.values()].sort(
    (a, b) =>
      (a.date || "9999").localeCompare(b.date || "9999") ||
      (a.kind === b.kind ? 0 : a.kind === "flight" ? -1 : 1),
  );
}

/** Rows whose work needs a worker right now: they show as delayed while none answers. */
export function isMoving(stage: Stage): boolean {
  return stage === "searching" || stage === "boarding";
}
