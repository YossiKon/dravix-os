// Tiny typed API client — every call goes to the dravix core on the same origin.

async function unwrap<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = "";
    try {
      const body = (await r.json()) as { detail?: string };
      detail = body.detail ?? "";
    } catch {
      /* not json */
    }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  return (await r.json()) as T;
}

export function apiGet<T>(url: string): Promise<T> {
  return fetch(url).then((r) => unwrap<T>(r));
}

export function apiSend<T>(url: string, method: "POST" | "PUT" | "DELETE", body?: unknown): Promise<T> {
  return fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
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
  store: { idle_motion?: boolean } & Record<string, unknown>;
}

export interface SecurityInfo {
  armed: boolean;
  total: number;
  photos: { day: string; name: string; size: number }[];
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
}

export interface Vitals {
  energy: number;
  food: number;
  fun: number;
  calm: number;
  lowest: string;
  nudges: boolean;
}
