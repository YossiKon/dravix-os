import type { Expression } from "../lib/types";

export interface ExprMeta {
  emoji: string;
  label: string;
  accent: string; // tailwind text color class
  ring: string; // tailwind border color when selected
}

// Tiny representations for each of the six StackChan faces.
export const EXPRESSION_META: Record<string, ExprMeta> = {
  neutral: {
    emoji: "·_·",
    label: "Neutral",
    accent: "text-soft",
    ring: "border-soft/60 bg-soft/10",
  },
  happy: {
    emoji: "^‿^",
    label: "Happy",
    accent: "text-phosphor",
    ring: "border-phosphor/60 bg-phosphor/10",
  },
  sad: {
    emoji: "╥﹏╥",
    label: "Sad",
    accent: "text-cyan",
    ring: "border-cyan/60 bg-cyan/10",
  },
  angry: {
    emoji: ">︿<",
    label: "Angry",
    accent: "text-fault",
    ring: "border-fault/60 bg-fault/10",
  },
  sleepy: {
    emoji: "-_-",
    label: "Sleepy",
    accent: "text-magenta",
    ring: "border-magenta/60 bg-magenta/10",
  },
  doubt: {
    emoji: "·_?",
    label: "Doubt",
    accent: "text-amber",
    ring: "border-amber/60 bg-amber/10",
  },
};

export function exprMeta(e: Expression | string): ExprMeta {
  return EXPRESSION_META[e] ?? EXPRESSION_META.neutral;
}
