// Thin fetch wrapper around the dravix-os REST API.
// Same-origin in production; Vite proxies /api to :8800 in dev.

import type {
  AiFunResponse,
  AiFunResult,
  AiProviderResponse,
  ChatResponse,
  ConfigResponse,
  EmotesResponse,
  ExportStore,
  Expression,
  FrigateCamerasResponse,
  FunResponse,
  FunResult,
  HaEntitiesResponse,
  HealthResponse,
  ImportResult,
  InboxPlayResponse,
  InboxResponse,
  InteractKind,
  Job,
  Memory,
  MemoryResponse,
  ModesResponse,
  MoodResponse,
  Persona,
  PersonaActiveResponse,
  PersonasResponse,
  ReactionRule,
  ReactionsResponse,
  RobotConfig,
  RobotConfigUpdate,
  Routine,
  RoutinesResponse,
  SayMoodResult,
  SayResult,
  ScheduleResponse,
  ScreenCard,
  ScreensResponse,
  ScreenState,
  ScreenUpdate,
  SetHomeResponse,
  StatusResponse,
  TimerResponse,
  VoiceResponse,
} from "./types";

/** Error carrying the HTTP status + backend-provided `detail`. */
export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { json?: unknown },
): Promise<T> {
  const { json, ...rest } = init ?? {};
  const headers = new Headers(rest.headers);
  if (json !== undefined) headers.set("Content-Type", "application/json");

  let res: Response;
  try {
    res = await fetch(path, {
      ...rest,
      headers,
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch (err) {
    // Network-level failure (server down, CORS, offline).
    throw new ApiError(
      0,
      err instanceof Error ? `Network error: ${err.message}` : "Network error",
    );
  }

  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body — keep status text */
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  // Some endpoints return tiny JSON like {ok:true}; tolerate empty bodies.
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  status: () => request<StatusResponse>("/api/status"),
  modes: () => request<ModesResponse>("/api/modes"),

  activateMode: (name: string) =>
    request<{ active: string | null }>(
      `/api/modes/${encodeURIComponent(name)}/activate`,
      { method: "POST" },
    ),
  deactivateMode: () =>
    request<{ active: string | null }>("/api/modes/deactivate", {
      method: "POST",
    }),

  say: (text: string, voice?: string) =>
    request<{ ok: boolean }>("/api/robot/say", {
      method: "POST",
      json: { text, ...(voice ? { voice } : {}) },
    }),

  face: (expression: Expression) =>
    request<{ ok: boolean }>("/api/robot/face", {
      method: "POST",
      json: { expression },
    }),

  head: (yaw: number, pitch: number, speed: number) =>
    request<{ ok: boolean }>("/api/robot/head", {
      method: "POST",
      json: { yaw, pitch, speed },
    }),

  // Capture the servos' CURRENT angles as the calibrated centre ("set home").
  setHeadHome: () =>
    request<SetHomeResponse>("/api/robot/head/home", { method: "POST" }),

  leds: (color: string, brightness: number) =>
    request<{ ok: boolean }>("/api/robot/leds", {
      method: "POST",
      json: { color, brightness },
    }),

  setIdleMotion: (enabled: boolean) =>
    request<{ idle_motion: boolean }>("/api/robot/idle-motion", {
      method: "PUT",
      json: { enabled },
    }),

  chat: (text: string, conversationId?: string, speak = false) =>
    request<ChatResponse>("/api/ai/chat", {
      method: "POST",
      json: {
        text,
        ...(conversationId ? { conversation_id: conversationId } : {}),
        speak,
      },
    }),

  /* ── Personality ──────────────────────────────────────────────────────── */
  mood: () => request<MoodResponse>("/api/mood"),

  interact: (kind: InteractKind) =>
    request<{ ok: boolean }>("/api/robot/interact", {
      method: "POST",
      json: { kind },
    }),

  emotes: () => request<EmotesResponse>("/api/emotes"),

  emote: (name: string) =>
    request<{ ok: boolean }>("/api/robot/emote", {
      method: "POST",
      json: { name },
    }),

  /* ── Announce ─────────────────────────────────────────────────────────── */
  announce: (text: string, expression?: string) =>
    request<{ ok: boolean }>("/api/announce", {
      method: "POST",
      json: { text, ...(expression ? { expression } : {}) },
    }),

  /* ── Config / settings ────────────────────────────────────────────────── */
  config: () => request<ConfigResponse>("/api/config"),

  setAiProvider: (provider: string | null) =>
    request<AiProviderResponse>("/api/config/ai_provider", {
      method: "PUT",
      json: { provider },
    }),

  setModeConfig: (name: string, config: Record<string, unknown>) =>
    request<{ ok: boolean }>(
      `/api/config/modes/${encodeURIComponent(name)}`,
      { method: "PUT", json: { config } },
    ),

  setModeDisabled: (name: string, disabled: boolean) =>
    request<{ ok: boolean }>(
      `/api/config/modes/${encodeURIComponent(name)}/disabled`,
      { method: "POST", json: { disabled } },
    ),

  /* ── Setup: robot config / entities / calibration ─────────────────────── */
  getRobotConfig: () => request<RobotConfig>("/api/robot/config"),

  putRobotConfig: (body: RobotConfigUpdate) =>
    request<RobotConfig>("/api/robot/config", { method: "PUT", json: body }),

  haEntities: (domains: string[]) => {
    const q = domains.length ? `?domains=${encodeURIComponent(domains.join(","))}` : "";
    return request<HaEntitiesResponse>(`/api/ha/entities${q}`);
  },

  getScreen: () => request<ScreenState>("/api/robot/screen"),

  putScreen: (body: ScreenUpdate) =>
    request<{ ok: boolean }>("/api/robot/screen", { method: "PUT", json: body }),

  /* ── Screens: HA entities shown on the robot's 3 display cards ─────────── */
  getScreens: () => request<ScreensResponse>("/api/screens"),

  putScreens: (screens: ScreenCard[]) =>
    request<ScreensResponse>("/api/screens", {
      method: "PUT",
      json: { screens },
    }),

  /* ── Cameras / Frigate ────────────────────────────────────────────────── */
  frigateCameras: () =>
    request<FrigateCamerasResponse>("/api/frigate/cameras"),

  frigateShow: (camera: string, alert: boolean) =>
    request<{ ok: boolean }>("/api/frigate/show", {
      method: "POST",
      json: { camera, alert },
    }),

  showImage: (url: string) =>
    request<{ ok: boolean }>("/api/robot/show_image", {
      method: "POST",
      json: { url },
    }),

  /* ── Reactions ────────────────────────────────────────────────────────── */
  reactions: () => request<ReactionsResponse>("/api/reactions"),

  setReactions: (reactions: ReactionRule[]) =>
    request<ReactionsResponse>("/api/reactions", {
      method: "PUT",
      json: { reactions },
    }),

  /* ── Schedule (daily jobs + timers) ───────────────────────────────────── */
  schedule: () => request<ScheduleResponse>("/api/schedule"),

  setSchedule: (schedule: Job[]) =>
    request<ScheduleResponse>("/api/schedule", {
      method: "PUT",
      json: { schedule },
    }),

  setTimer: (seconds: number, label?: string, say?: string) =>
    request<TimerResponse>("/api/timer", {
      method: "POST",
      json: {
        seconds,
        ...(label ? { label } : {}),
        ...(say ? { say } : {}),
      },
    }),

  /* ── Personas ─────────────────────────────────────────────────────────── */
  personas: () => request<PersonasResponse>("/api/personas"),

  setPersonas: (personas: Persona[]) =>
    request<PersonasResponse>("/api/personas", {
      method: "PUT",
      json: { personas },
    }),

  setActivePersona: (name: string | null) =>
    request<PersonaActiveResponse>("/api/personas/active", {
      method: "POST",
      json: { name },
    }),

  /* ── Voice (TTS) ──────────────────────────────────────────────────────── */
  voice: () => request<VoiceResponse>("/api/voice"),

  setVoice: (voice: string | null) =>
    request<{ voice: string | null }>("/api/voice", {
      method: "PUT",
      json: { voice },
    }),

  setVoices: (voices: string[]) =>
    request<{ voices: string[] }>("/api/voices", {
      method: "PUT",
      json: { voices },
    }),

  /* ── Fun & voice ──────────────────────────────────────────────────────── */
  fun: () => request<FunResponse>("/api/fun"),

  playFun: (name: string) =>
    request<FunResult>(`/api/fun/${encodeURIComponent(name)}`, {
      method: "POST",
    }),

  sayTime: () => request<SayResult>("/api/say/time", { method: "POST" }),

  sayWeather: () => request<SayResult>("/api/say/weather", { method: "POST" }),

  sayAgenda: () => request<SayResult>("/api/say/agenda", { method: "POST" }),

  sayMood: () => request<SayMoodResult>("/api/say/mood", { method: "POST" }),

  /* ── AI party tricks ──────────────────────────────────────────────────── */
  aiFun: () => request<AiFunResponse>("/api/ai/fun"),

  playAiFun: (kind: string) =>
    request<AiFunResult>(`/api/ai/fun/${encodeURIComponent(kind)}`, {
      method: "POST",
    }),

  /* ── Memory (facts) ───────────────────────────────────────────────────── */
  memory: () => request<MemoryResponse>("/api/memory"),

  addMemory: (text: string) =>
    request<Memory>("/api/memory", { method: "POST", json: { text } }),

  deleteMemory: (id: string) =>
    request<{ ok: boolean }>(`/api/memory/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  /* ── Routines (named action macros) ───────────────────────────────────── */
  routines: () => request<RoutinesResponse>("/api/routines"),

  setRoutines: (routines: Routine[]) =>
    request<RoutinesResponse>("/api/routines", {
      method: "PUT",
      json: { routines },
    }),

  runRoutine: (name: string) =>
    request<{ ok: boolean }>(
      `/api/routines/${encodeURIComponent(name)}/run`,
      { method: "POST" },
    ),

  /* ── Inbox (queued / spoken messages) ─────────────────────────────────── */
  inbox: () => request<InboxResponse>("/api/inbox"),

  notify: (text: string, speak = true) =>
    request<{ ok: boolean }>("/api/notify", {
      method: "POST",
      json: { text, speak },
    }),

  playInbox: () =>
    request<InboxPlayResponse>("/api/inbox/play", { method: "POST" }),

  clearInbox: () => request<{ ok: boolean }>("/api/inbox", { method: "DELETE" }),

  /* ── Backup & restore (full config export/import) ─────────────────────── */
  exportStore: () => request<ExportStore>("/api/export"),

  importStore: (store: ExportStore) =>
    request<ImportResult>("/api/import", { method: "POST", json: { store } }),
};
