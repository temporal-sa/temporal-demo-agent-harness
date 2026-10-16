import type { ToolPart } from "@temporalio/agent-harness-client";
import { usd } from "./format.ts";

/** The callback tool Monty uses to ask the traveler to pick between trip options. */
export const CHOICE_TOOL = "ask_traveler_to_choose";

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

export const FARE_LABEL: Record<Fare, string> = { economy: "Economy", premium: "Premium", business: "Business" };

/** The question and options a choice call carries (`{request: {...}}`, like every host call). */
export function choiceRequest(part: ToolPart): { question: string; options: Option[] } {
  const request = (part.input as { request?: { question?: string; options?: Option[] } }).request;
  return { question: request?.question ?? "", options: request?.options ?? [] };
}

/** The traveler's answer, read off the tool's output, which prints the model Python-style. */
export function answeredChoice(part: ToolPart): Choice | null {
  if (!part.output) return null;
  const field = (name: string) => new RegExp(`${name}='([^']*)'`).exec(part.output ?? "")?.[1] ?? null;
  return { option_id: field("option_id"), fare: field("fare") as Fare | null, comment: field("comment") };
}

/** One line for the conversation: what was picked, or what the traveler asked for instead. */
export function choiceSummary(part: ToolPart): string {
  const choice = answeredChoice(part);
  if (!choice) return "";
  if (!choice.option_id) return choice.comment ? `None of these: “${choice.comment}”` : "None of these";
  const option = choiceRequest(part).options.find((o) => o.option_id === choice.option_id);
  const fare = option?.fares.find((f) => f.level === choice.fare);
  return [option?.title ?? choice.option_id, choice.fare && FARE_LABEL[choice.fare], fare && usd.format(fare.total_usd)]
    .filter(Boolean)
    .join(" · ");
}
