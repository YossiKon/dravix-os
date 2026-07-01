import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { useToasts } from "../hooks/useToasts";
import type {
  CalibrationAxis,
  Calibration,
  HaEntity,
  RobotConfig,
  RobotDriver,
  RoleDef,
  ScreenState,
} from "../lib/types";
import { Button, Chip, Dot, Panel, Toggle, cx, errMsg } from "../components/ui";

const DRIVERS: { id: RobotDriver; label: string }[] = [
  { id: "mock", label: "mock" },
  { id: "ha", label: "ha" },
  { id: "mcp", label: "mcp" },
];

const DRIVER_HINT =
  "ha = control the StackChan through its Home Assistant/ESPHome entities";

// Roles that participate in head calibration (must be axis-mapped entities).
const YAW_ROLE = "head_yaw";
const PITCH_ROLE = "head_pitch";

const inputCls = cx(
  "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
  "font-mono text-sm text-ink placeholder:text-mute/70",
  "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

const selectCls = cx(
  "w-full rounded-lg border border-line bg-panel-2 px-2.5 py-2",
  "font-mono text-[12px] text-ink",
  "focus:border-phosphor/50 focus:outline-none",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

/**
 * Setup — configure the robot entirely from dravix-os (driver, HA entity
 * mapping, head servo calibration, OLED screen protection). Always visible;
 * it is how the robot gets wired up in the first place.
 *
 * Self-contained: fetches robot config + HA entities + screen state, edits a
 * local draft, and saves via PUT /api/robot/config (+ PUT /api/robot/screen).
 */
export function SetupPage() {
  const toasts = useToasts();

  const [config, setConfig] = useState<RobotConfig | null>(null);
  const [haEnts, setHaEnts] = useState<HaEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Editable draft (mirrors config; committed on Save).
  const [driver, setDriver] = useState<RobotDriver>("mock");
  const [entities, setEntities] = useState<Record<string, string>>({});
  const [calibration, setCalibration] = useState<Calibration>({});

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Adopt a fresh config into both the source-of-truth + the editable draft.
  const adopt = useCallback((c: RobotConfig) => {
    setConfig(c);
    setDriver(c.driver);
    setEntities({ ...c.entities });
    setCalibration({
      yaw: { ...(c.calibration.yaw ?? {}) },
      pitch: { ...(c.calibration.pitch ?? {}) },
    });
  }, []);

  // Union of every domain any role accepts — one HA fetch, filtered per role.
  const allDomains = useMemo(() => {
    const set = new Set<string>();
    for (const r of config?.roles ?? []) for (const d of r.domains) set.add(d);
    return [...set];
  }, [config?.roles]);

  const loadEntities = useCallback(
    async (domains: string[]) => {
      if (domains.length === 0) return;
      try {
        const r = await api.haEntities(domains);
        if (mounted.current) setHaEnts(r.entities ?? []);
      } catch (err) {
        if (mounted.current) toasts.error(errMsg(err));
      }
    },
    [toasts],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const c = await api.getRobotConfig();
      if (!mounted.current) return;
      adopt(c);
      // Once we know the roles, pull the HA entities for their domains.
      const domains = new Set<string>();
      for (const r of c.roles) for (const d of r.domains) domains.add(d);
      if (c.ha_configured) await loadEntities([...domains]);
    } catch (err) {
      if (mounted.current) toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [adopt, loadEntities, toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const haConfigured = config?.ha_configured ?? false;

  function setEntity(key: string, value: string) {
    setEntities((e) => ({ ...e, [key]: value }));
  }

  function setAxis(axis: "yaw" | "pitch", patch: Partial<CalibrationAxis>) {
    setCalibration((c) => ({ ...c, [axis]: { ...(c[axis] ?? {}), ...patch } }));
  }

  async function save() {
    setSaving(true);
    try {
      // Drop blank entity selections so we send a clean mapping.
      const cleanEntities: Record<string, string> = {};
      for (const [k, v] of Object.entries(entities)) if (v) cleanEntities[k] = v;
      // Calibration is now center + invert only — min/max are handled by the driver.
      const cleanCalibration: Calibration = {};
      for (const ax of ["yaw", "pitch"] as const) {
        const a = calibration[ax];
        if (a) cleanCalibration[ax] = { center: a.center, invert: a.invert };
      }
      const res = await api.putRobotConfig({
        driver,
        entities: cleanEntities,
        calibration: cleanCalibration,
      });
      if (mounted.current) adopt(res);
      if (res.error) toasts.error(res.error);
      else
        toasts.ok(
          `Saved · ${res.online ? "online" : "offline"} · ${res.capabilities.length} caps`,
        );
      // Domains may have changed (driver switch) — reload entity list.
      if (mounted.current && res.ha_configured) {
        const domains = new Set<string>();
        for (const r of res.roles) for (const d of r.domains) domains.add(d);
        await loadEntities([...domains]);
      }
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setSaving(false);
    }
  }

  if (loading && !config) {
    return (
      <div className="space-y-5">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-40 animate-pulse rounded-2xl bg-line/40" />
        ))}
      </div>
    );
  }

  if (!config) {
    return (
      <Panel eyebrow="configuration" title="Setup">
        <p className="font-mono text-xs text-mute">
          Robot config unavailable — is the core service reachable?
        </p>
      </Panel>
    );
  }

  const yawSet = !!entities[YAW_ROLE];
  const pitchSet = !!entities[PITCH_ROLE];
  const calibratable = yawSet || pitchSet;

  return (
    <div className="space-y-5">
      <DriverSection
        config={config}
        driver={driver}
        onDriver={setDriver}
        haConfigured={haConfigured}
      />

      <EntitiesSection
        roles={config.roles}
        entities={entities}
        haEnts={haEnts}
        allDomains={allDomains}
        haConfigured={haConfigured}
        onChange={setEntity}
      />

      {calibratable && (
        <CalibrationSection
          calibration={calibration}
          yawSet={yawSet}
          pitchSet={pitchSet}
          onAxis={setAxis}
        />
      )}

      <ScreenSection anySet={calibratable} entities={entities} />

      {/* Sticky-ish save bar */}
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-line bg-panel/80 px-5 py-4 shadow-panel">
        <div className="flex items-center gap-2 font-mono text-[11px] text-mute">
          <Dot color={config.online ? "green" : "red"} pulse={config.online} />
          {config.online ? "robot online" : "robot offline"}
          {config.last_error && (
            <span className="truncate text-fault">· {config.last_error}</span>
          )}
        </div>
        <Button variant="primary" loading={saving} onClick={save}>
          ▸ Save configuration
        </Button>
      </div>
    </div>
  );
}

/* ── 1. Driver ──────────────────────────────────────────────────────────── */
function DriverSection({
  config,
  driver,
  onDriver,
  haConfigured,
}: {
  config: RobotConfig;
  driver: RobotDriver;
  onDriver: (d: RobotDriver) => void;
  haConfigured: boolean;
}) {
  // Only offer drivers the backend actually registered (fall back to all three).
  const available = new Set(config.drivers ?? []);
  const options = DRIVERS.filter((d) => available.size === 0 || available.has(d.id));

  return (
    <Panel
      eyebrow="backend"
      title="Driver"
      right={
        <div className="flex items-center gap-2 font-mono text-[11px] text-mute">
          <Dot color={config.online ? "green" : "red"} pulse={config.online} />
          {config.online ? "online" : "offline"}
        </div>
      }
    >
      <div className="space-y-3">
        {/* Segmented control */}
        <div className="inline-flex gap-1 rounded-xl border border-line bg-panel/70 p-1">
          {options.map((d) => {
            const selected = driver === d.id;
            return (
              <button
                key={d.id}
                onClick={() => onDriver(d.id)}
                className={cx(
                  "rounded-lg px-4 py-2 font-mono text-[12px] font-500 uppercase tracking-[0.08em] transition-all",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-phosphor/40",
                  selected
                    ? "bg-phosphor/15 text-phosphor shadow-[0_0_18px_-8px_rgba(93,255,160,0.6)]"
                    : "text-soft hover:bg-panel-2 hover:text-ink",
                )}
              >
                {d.label}
              </button>
            );
          })}
        </div>

        <p className="font-mono text-[11px] text-mute">{DRIVER_HINT}</p>

        {driver === "ha" && !haConfigured && (
          <p className="rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-[11px] leading-relaxed text-amber">
            Home Assistant URL + token must be set in the add-on config before the
            ha driver can reach the robot.
          </p>
        )}

        {/* Live capabilities */}
        <div>
          <div className="eyebrow mb-2">capabilities</div>
          {config.capabilities.length === 0 ? (
            <p className="font-mono text-[11px] text-mute">
              None reported yet — save a driver + entities to probe the robot.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {config.capabilities.map((c) => (
                <Chip key={c} tone="on">
                  {c}
                </Chip>
              ))}
            </div>
          )}
        </div>
      </div>
    </Panel>
  );
}

/* ── 2. Entities ────────────────────────────────────────────────────────── */
function EntitiesSection({
  roles,
  entities,
  haEnts,
  allDomains,
  haConfigured,
  onChange,
}: {
  roles: RoleDef[];
  entities: Record<string, string>;
  haEnts: HaEntity[];
  allDomains: string[];
  haConfigured: boolean;
  onChange: (key: string, value: string) => void;
}) {
  return (
    <Panel
      eyebrow="mapping"
      title="Entities"
      right={
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {haConfigured ? `${haEnts.length} ha entities` : "ha not connected"}
        </span>
      }
    >
      {!haConfigured ? (
        <p className="font-mono text-[11px] text-mute">
          Connect Home Assistant first — set the HA URL + token in the add-on
          config, then pick the driver above.
        </p>
      ) : (
        <div className="space-y-2">
          {roles.map((role) => (
            <EntityRow
              key={role.key}
              role={role}
              selected={entities[role.key] ?? ""}
              haEnts={haEnts}
              disabled={!haConfigured}
              onChange={(v) => onChange(role.key, v)}
            />
          ))}
          <p className="pt-1 font-mono text-[10px] leading-relaxed text-mute">
            Filtered by domain per role ({allDomains.join(", ") || "—"}). These map
            the robot's functions to your HA/ESPHome entities.
          </p>
        </div>
      )}
    </Panel>
  );
}

function EntityRow({
  role,
  selected,
  haEnts,
  disabled,
  onChange,
}: {
  role: RoleDef;
  selected: string;
  haEnts: HaEntity[];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const domains = new Set(role.domains);
  const options = haEnts.filter((e) => domains.has(e.domain));
  // Keep the current selection visible even if it's not in the fetched list.
  const missing = selected && !options.some((e) => e.entity_id === selected);

  return (
    <div className="grid grid-cols-1 items-center gap-2 rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5 sm:grid-cols-[1fr_1.4fr]">
      <div className="min-w-0">
        <div className="truncate font-display text-sm font-600 text-ink">
          {role.label}
        </div>
        <div className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {role.domains.join(" / ")}
        </div>
      </div>
      <select
        value={selected}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={selectCls}
      >
        <option value="">— none —</option>
        {missing && (
          <option value={selected}>{selected} (current)</option>
        )}
        {options.map((e) => (
          <option key={e.entity_id} value={e.entity_id}>
            {e.name} · {e.entity_id}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ── 3. Head calibration ────────────────────────────────────────────────── */
function CalibrationSection({
  calibration,
  yawSet,
  pitchSet,
  onAxis,
}: {
  calibration: Calibration;
  yawSet: boolean;
  pitchSet: boolean;
  onAxis: (axis: "yaw" | "pitch", patch: Partial<CalibrationAxis>) => void;
}) {
  const toasts = useToasts();
  const [homing, setHoming] = useState(false);

  // Live nudge: head values are NORMALISED in [-1,1] (backend applies center/invert).
  const test = useCallback(
    async (yaw: number, pitch: number) => {
      try {
        await api.head(yaw, pitch, 0.5);
      } catch (err) {
        toasts.error(errMsg(err));
      }
    },
    [toasts],
  );

  // "Set current as home": capture the servos' present angles as the neutral
  // centre, then reflect the returned centres in the draft's Center fields.
  const setHome = useCallback(async () => {
    setHoming(true);
    try {
      const res = await api.setHeadHome();
      if (res.error) {
        toasts.error(res.error);
        return;
      }
      const yawCenter = res.calibration.yaw?.center;
      const pitchCenter = res.calibration.pitch?.center;
      if (yawCenter !== undefined) onAxis("yaw", { center: yawCenter });
      if (pitchCenter !== undefined) onAxis("pitch", { center: pitchCenter });
      const parts: string[] = [];
      if (res.captured.yaw !== null) parts.push(`yaw ${res.captured.yaw}°`);
      if (res.captured.pitch !== null) parts.push(`pitch ${res.captured.pitch}°`);
      toasts.ok(
        `Home set${parts.length ? ` · ${parts.join(" · ")}` : ""} — save to keep`,
      );
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      setHoming(false);
    }
  }, [onAxis, toasts]);

  return (
    <Panel eyebrow="servos" title="Head Calibration">
      <div className="space-y-4">
        <p className="font-mono text-[11px] leading-relaxed text-mute">
          Center = the servo value that looks straight; use Set current as HOME to
          capture it. If the head aims the wrong way, toggle Invert. The driver
          clamps to the servo's hardware range automatically.
        </p>

        {/* Live test pad */}
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-panel-2/40 px-3.5 py-3">
          <span className="mr-1 font-mono text-[10px] uppercase tracking-wider text-mute">
            test
          </span>
          <Button variant="subtle" onClick={() => test(-0.6, 0)}>
            ◀ Left
          </Button>
          <Button variant="subtle" onClick={() => test(0.6, 0)}>
            ▶ Right
          </Button>
          <Button variant="subtle" onClick={() => test(0, 0.6)}>
            ▲ Up
          </Button>
          <Button variant="subtle" onClick={() => test(0, -0.6)}>
            ▼ Down
          </Button>
          <Button variant="primary" onClick={() => test(0, 0)}>
            ⌖ Center
          </Button>
        </div>

        {/* Set current head position as the neutral home/centre */}
        <div className="rounded-xl border border-phosphor/30 bg-phosphor/[0.04] px-3.5 py-3">
          <Button variant="primary" loading={homing} onClick={setHome}>
            ⌖ Set current as HOME
          </Button>
          <p className="mt-2 font-mono text-[10px] leading-relaxed text-mute">
            Position the head so it looks straight ahead (move it in Home
            Assistant or with the test buttons), then click — dravix saves the
            current angle as the neutral centre.
          </p>
        </div>

        {yawSet && (
          <AxisCalibration
            title="Yaw (left / right)"
            axis={calibration.yaw ?? {}}
            onChange={(patch) => onAxis("yaw", patch)}
          />
        )}
        {pitchSet && (
          <AxisCalibration
            title="Pitch (up / down)"
            axis={calibration.pitch ?? {}}
            onChange={(patch) => onAxis("pitch", patch)}
          />
        )}
      </div>
    </Panel>
  );
}

function AxisCalibration({
  title,
  axis,
  onChange,
}: {
  title: string;
  axis: CalibrationAxis;
  onChange: (patch: Partial<CalibrationAxis>) => void;
}) {
  // Empty string → undefined (blank center falls back to the driver default).
  const num = (v: string): number | undefined =>
    v.trim() === "" ? undefined : Number(v);

  return (
    <div className="rounded-xl border border-line bg-panel-2/30 p-4">
      <div className="eyebrow mb-3 flex items-center gap-2">
        {title}
        <span className="h-px flex-1 bg-line/70" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <NumField
          label="center"
          hint="looks straight"
          value={axis.center}
          onChange={(v) => onChange({ center: num(v) })}
        />
        <div className="flex flex-col justify-between">
          <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
            invert
          </span>
          <div className="mt-1 flex h-[38px] items-center">
            <Toggle
              on={axis.invert ?? false}
              label="Invert axis"
              onChange={(next) => onChange({ invert: next })}
            />
          </div>
        </div>
      </div>
      <p className="mt-2 font-mono text-[10px] text-mute">
        nudge Center until the head looks straight ahead
      </p>
    </div>
  );
}

function NumField({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
        {label}
      </span>
      <input
        type="number"
        value={value ?? ""}
        placeholder={hint}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      />
    </label>
  );
}

/* ── 4. Screen (OLED burn-in protection) ────────────────────────────────── */
function ScreenSection({
  anySet,
  entities,
}: {
  anySet: boolean;
  entities: Record<string, string>;
}) {
  const toasts = useToasts();
  const [screen, setScreen] = useState<ScreenState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saver, setSaver] = useState(0);
  const [sleep, setSleep] = useState(0);

  // Are the screensaver/sleep number entities mapped in the current draft?
  const hasScreenEntities =
    !!entities["screensaver_number"] || !!entities["sleep_number"];

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const s = await api.getScreen();
      if (mounted.current) {
        setScreen(s);
        setSaver(s.screensaver_min ?? 0);
        setSleep(s.sleep_min ?? 0);
      }
    } catch (err) {
      if (mounted.current) toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function save() {
    setSaving(true);
    try {
      await api.putScreen({ screensaver_min: saver, sleep_min: sleep });
      toasts.ok("Screen protection saved");
      await refresh();
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setSaving(false);
    }
  }

  const supported = screen?.supported ?? false;

  // Nothing loaded yet — keep the slot quiet.
  if (loading && !screen) {
    return (
      <Panel eyebrow="display" title="Screen">
        <div className="h-16 animate-pulse rounded-xl bg-line/40" />
      </Panel>
    );
  }

  if (!supported) {
    // Muted placeholder only when the user hasn't wired the number entities yet.
    return (
      <Panel eyebrow="display" title="Screen">
        <p className="font-mono text-[11px] text-mute">
          {hasScreenEntities || anySet
            ? "Screen protection isn't supported by this backend."
            : "Set the screensaver/sleep number entities above first."}
        </p>
      </Panel>
    );
  }

  return (
    <Panel
      eyebrow="display"
      title="Screen (OLED burn-in protection)"
      right={
        <Button variant="primary" loading={saving} onClick={save}>
          Save
        </Button>
      }
    >
      <div className="space-y-4">
        <MinuteSlider
          label="screensaver after"
          value={saver}
          onChange={setSaver}
        />
        <MinuteSlider label="sleep after" value={sleep} onChange={setSleep} />
        <p className="font-mono text-[10px] leading-relaxed text-mute">
          Sleep = black screen, the face stops moving until you touch it or say
          "ok nabu".
        </p>
      </div>
    </Panel>
  );
}

function MinuteSlider({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {label}
        </span>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min={0}
            max={120}
            value={value}
            onChange={(e) => onChange(Math.max(0, Number(e.target.value) || 0))}
            className="w-16 rounded-lg border border-line bg-void/60 px-2 py-1 text-right font-mono text-xs text-ink focus:border-phosphor/50 focus:outline-none"
          />
          <span className="font-mono text-[10px] text-mute">min</span>
        </div>
      </div>
      <input
        type="range"
        className="slider"
        min={0}
        max={120}
        step={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
