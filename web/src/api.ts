// Tiny typed API client — every call goes to the dravix core on the same origin.
//
// URLS ARE RELATIVE to the page's base, not root-absolute: the app is served both at
// http://host:8800/ AND under Home Assistant ingress (/api/hassio_ingress/<token>/),
// where "/api/..." would resolve against HA itself and 401. `apiUrl` makes both work.
const BASE = new URL(".", window.location.href);

export function apiUrl(path: string): string {
  return new URL(path.replace(/^\//, ""), BASE).toString();
}

export function wsUrl(path: string): string {
  const u = new URL(path.replace(/^\//, ""), BASE);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

// AbortSignal.timeout is missing on older Safari/WebViews — degrade to "no deadline"
// instead of throwing synchronously on every call (which rendered the app blank).
const deadline = (ms: number): AbortSignal | undefined =>
  typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(ms) : undefined;

async function unwrap<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = "";
    try {
      const body = (await r.json()) as { detail?: unknown };
      const d = body.detail;
      if (typeof d === "string") detail = d;
      // FastAPI validation errors are an array of {msg, loc, ...} — surface the messages,
      // not "[object Object]".
      else if (Array.isArray(d))
        detail = d
          .map((it) => (it && typeof it === "object" && "msg" in it ? String((it as { msg: unknown }).msg) : JSON.stringify(it)))
          .join("; ");
      else if (d != null) detail = JSON.stringify(d);
    } catch {
      /* not json */
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  return (await r.json()) as T;
}

// A hung backend must not leave spinners stuck forever — every call gets a deadline.
export function apiGet<T>(url: string, timeoutMs = 15000): Promise<T> {
  return fetch(apiUrl(url), { signal: deadline(timeoutMs) }).then((r) => unwrap<T>(r));
}

export function apiSend<T>(
  url: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
  timeoutMs = 60000,
): Promise<T> {
  return fetch(apiUrl(url), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: deadline(timeoutMs),
  }).then((r) => unwrap<T>(r));
}

// ── shapes ────────────────────────────────────────────────────────────────────
export interface Role {
  key: string;
  label: string;
  domains: string[];
}

export interface RobotConfig {
  driver: string;
  drivers: string[];
  roles: Role[];
  entities: Record<string, string>;
  calibration: Record<string, { center?: number | null; invert?: boolean }>;
  capabilities: string[];
  online: boolean;
  last_error: string;
  ha_configured: boolean;
  robot_name?: string;
  error?: string | null;
}

export interface Live {
  supported: boolean;
  state: string | null;
  heard: string | null;
  reply: string | null;
  battery: number | null;
}

export interface HAEntity {
  entity_id: string;
  name: string;
  domain: string;
  state?: string | null;
}

export interface ScreenCard {
  title: string;
  entities: string[];
}

export interface ClimateState {
  state: string | null;
  current_temperature: number | null;
  temperature: number | null;
  hvac_modes: string[] | null;
  min_temp: number | null;
  max_temp: number | null;
  target_temp_step: number | null;
}

export interface Health {
  version: string;
}

export interface AppConfig {
  ai_provider: string;
  ai_available: boolean;
  providers: string[];
  local_only: boolean;
  store: { idle_motion?: boolean; spontaneous_speech?: boolean } & Record<string, unknown>;
}

export interface PluginMode {
  name: string;
  description: string;
  kind: "foreground" | "ambient";
  active: boolean;
  disabled: boolean;
  config: Record<string, unknown>;
}

export interface SecurityPhoto {
  day: string;
  name: string;
  size: number;
  ts?: string;
}

export interface SecurityClip {
  day: string;
  name: string;
  size: number;
  ts?: string;
}

export interface SecurityInfo {
  armed: boolean;
  recording?: boolean;
  total: number;
  photos: SecurityPhoto[];
}

export interface AgentEntry {
  name: string;
  state: string;
  text: string;
  updated_at: string;
  stale: boolean;
}

export interface AgentPermission {
  id: string;
  agent: string;
  tool: string;
  summary: string;
  decision: string; // pending | approved | rejected | expired
  created_at: string;
}

export interface AgentStatus {
  winner: AgentEntry | null;
  agents: AgentEntry[];
  display: string; // bubble | badge | both | off
  primary: string; // pinned agent name, or "" = auto (most urgent)
  muted: string[]; // agent names whose speech is silenced
  approvals: boolean; // master on/off for on-robot tool approvals
  palette: Record<string, { color: string; glyph: string }>;
  permission: AgentPermission | null;
}

export interface SecurityDay {
  day: string;
  count: number;
  videos: number;
  bytes: number;
  has_video: boolean;
}

export interface Updates {
  addon_version: string;
  addon_latest: string | null;
  addon_update: boolean;
  fw_bundled: string | null;
  fw_robot: string | null;
  fw_update: boolean;
  checked_online: boolean;
}

export interface ScreenTimers {
  supported: boolean;
  screensaver_min: number | null;
  sleep_min: number | null;
  brightness?: number | null;
}

export interface Vitals {
  energy: number;
  food: number;
  fun: number;
  calm: number;
  lowest: string;
  nudges: boolean;
}

export interface PersonalityAxis {
  key: string;
  value: number; // -1..+1
  left_he: string;
  left_en: string;
  right_he: string;
  right_en: string;
}

export interface Personality {
  axes: PersonalityAxis[];
  days: number;
  settled: boolean;
}
