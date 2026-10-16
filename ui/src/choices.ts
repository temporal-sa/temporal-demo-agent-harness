import type { ToolPart } from "@temporalio/agent-harness-client";
import { usd } from "./format.ts";

/** The callback tools Ziggy uses to ask the traveler to pick between trip options or hotels. */
export const CHOICE_TOOL = "ask_traveler_to_choose";
export const HOTEL_TOOL = "ask_traveler_to_choose_hotel";
export const isChoiceTool = (name: string) => name === CHOICE_TOOL || name === HOTEL_TOOL;

export type Fare = "economy" | "premium" | "business";

export interface Leg {
  flight_id: string;
  origin: string;
  destination: string;
  date: string;
  airline: string;
  departure_time: string;
  arrival_time: string;
  stops: number;
}

export interface Option {
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

export interface HotelOption {
  hotel_id: string;
  name: string;
  neighborhood: string;
  star_rating: number;
  price_per_night_usd: number;
  total_usd: number;
  note?: string | null;
}

export interface HotelChoice {
  hotel_id: string | null;
  comment: string | null;
}

export const FARE_LABEL: Record<Fare, string> = { economy: "Economy", premium: "Premium", business: "Business" };

/** The question and options a choice call carries (`{request: {...}}`, like every host call). */
export function choiceRequest(part: ToolPart): { question: string; options: Option[] } {
  const request = (part.input as { request?: { question?: string; options?: Option[] } }).request;
  return { question: request?.question ?? "", options: request?.options ?? [] };
}

/** The hotels a hotel choice call carries, for one city and stay. */
export function hotelRequest(part: ToolPart): {
  question: string;
  city: string;
  check_in: string;
  check_out: string;
  options: HotelOption[];
} {
  const request = (part.input as { request?: Partial<ReturnType<typeof hotelRequest>> }).request ?? {};
  return {
    question: request.question ?? "",
    city: request.city ?? "",
    check_in: request.check_in ?? "",
    check_out: request.check_out ?? "",
    options: request.options ?? [],
  };
}

/** The traveler's answer, read off the tool's output, which prints the model Python-style. */
export function answeredChoice(part: ToolPart): Choice | null {
  if (!part.output) return null;
  const field = (name: string) => new RegExp(`${name}='([^']*)'`).exec(part.output ?? "")?.[1] ?? null;
  return { option_id: field("option_id"), fare: field("fare") as Fare | null, comment: field("comment") };
}

/** One line for the conversation: what was picked, or what the traveler asked for instead. */
export function choiceSummary(part: ToolPart): string {
  if (part.toolName === HOTEL_TOOL) return hotelSummary(part);
  const choice = answeredChoice(part);
  if (!choice) return "";
  if (!choice.option_id) return choice.comment ? `None of these: “${choice.comment}”` : "None of these";
  const option = choiceRequest(part).options.find((o) => o.option_id === choice.option_id);
  const fare = option?.fares.find((f) => f.level === choice.fare);
  return [option?.title ?? choice.option_id, choice.fare && FARE_LABEL[choice.fare], fare && usd.format(fare.total_usd)]
    .filter(Boolean)
    .join(" · ");
}

function hotelSummary(part: ToolPart): string {
  if (!part.output) return "";
  const field = (name: string) => new RegExp(`${name}='([^']*)'`).exec(part.output ?? "")?.[1] ?? null;
  const id = field("hotel_id");
  const comment = field("comment");
  if (!id) return comment ? `None of these: “${comment}”` : "None of these";
  const hotel = hotelRequest(part).options.find((h) => h.hotel_id === id);
  return hotel ? `${hotel.name} · ${usd.format(hotel.total_usd)}` : id;
}
