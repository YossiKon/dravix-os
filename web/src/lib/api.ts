// Thin fetch wrapper around the dravix-os REST API.
// Same-origin in production; Vite proxies /api to :8800 in dev.

import type {
  AiProviderResponse,
  ChatResponse,
  ConfigResponse,
  EmotesResponse,
  Expression,
  FrigateCamerasResponse,
  HealthResponse,
  InteractKind,
  ModesResponse,
  MoodResponse,
  ReactionRule,
  ReactionsResponse,
  StatusResponse,
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

  leds: (color: string, brightness: number) =>
    request<{ ok: boolean }>("/api/robot/leds", {
      method: "POST",
      json: { color, brightness },
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
};
