// Shared types mirroring the dravix-os core API contract.

export type Expression =
  | "neutral"
  | "happy"
  | "sad"
  | "angry"
  | "sleepy"
  | "doubt";

export const EXPRESSIONS: Expression[] = [
  "neutral",
  "happy",
  "sad",
  "angry",
  "sleepy",
  "doubt",
];

export interface RobotState {
  online: boolean;
  driver: string;
  transport: string;
  capabilities: string[];
  expression: string;
  head_yaw: number;
  head_pitch: number;
  last_said: string;
  last_error: string;
  updated_at?: number | string;
}

export interface Mood {
  valence: number; // -1..1
  arousal: number; // 0..1
  affection: number; // 0..1
  mood: string;
  expression: string;
}

export interface StatusResponse {
  robot: RobotState;
  active_mode: string | null;
  ambient_modes: string[];
  ai_provider: string | null;
  ai_available: boolean;
  mood?: Mood;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export type ModeKind = "foreground" | "ambient";

export interface ModeInfo {
  name: string;
  description: string;
  kind: ModeKind;
  active: boolean;
  disabled?: boolean;
}

export interface ModesResponse {
  modes: ModeInfo[];
  active: string | null;
}

export interface ChatResponse {
  text: string;
  conversation_id: string;
}

// A WebSocket event from /ws/events.
export interface BusEvent {
  type: string;
  data: Record<string, unknown>;
  ts: number;
}

// Known capability identifiers used to gate manual controls.
export const CAP = {
  say: "say",
  setFace: "set_face",
  moveHead: "move_head",
  setLeds: "set_leds",
} as const;

/* ── Personality ─────────────────────────────────────────────────────────── */
export type InteractKind = "pet" | "tap" | "touched" | "spoke";

export type MoodResponse = Mood;

export interface EmotesResponse {
  emotes: string[];
}

/* ── Config / settings ───────────────────────────────────────────────────── */
export interface ConfigResponse {
  store: Record<string, unknown>;
  ai_provider: string | null;
  ai_available: boolean;
  providers: string[];
  local_only: boolean;
  cloud_providers: string[];
}

export interface AiProviderResponse {
  ai_provider: string | null;
  ai_available: boolean;
  error?: string | null;
}

/* ── Cameras / Frigate ───────────────────────────────────────────────────── */
export interface FrigateCamerasResponse {
  cameras: string[];
}

/* ── Reactions (event → action rules) ────────────────────────────────────── */
export interface ReactionRule {
  name: string;
  on: string;
  match?: Record<string, unknown>;
  throttle_s?: number;
  face?: string;
  leds?: { color: string; brightness: number };
  say?: string;
  frigate_show?: string;
  activate_mode?: string;
  enabled?: boolean;
}

export interface ReactionsResponse {
  reactions: ReactionRule[];
}

/* ── Schedule (daily jobs + timers) ──────────────────────────────────────── */
export interface JobAction {
  say?: string;
  face?: string;
  emote?: string;
  activate_mode?: string;
}

export interface Job {
  name: string;
  at: string; // "HH:MM"
  days?: number[]; // 0=Mon .. 6=Sun
  enabled?: boolean;
  action: JobAction;
}

export interface ScheduleResponse {
  schedule: Job[];
}

export interface TimerResponse {
  id: string;
  seconds: number;
  label?: string;
}

/* ── Personas ────────────────────────────────────────────────────────────── */
export interface Persona {
  name: string;
  system_prompt: string;
  voice?: string;
  default_expression?: string;
}

export interface PersonasResponse {
  personas: Persona[];
  active: string | null;
}

export interface PersonaActiveResponse {
  active: string | null;
  ai_available: boolean;
  error?: string | null;
}
