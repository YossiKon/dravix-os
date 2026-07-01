import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useToasts } from "../hooks/useToasts";
import type { ClimateState, HaEntity } from "../lib/types";
import { Button, Panel, cx, errMsg } from "../components/ui";

const selectCls = cx(
  "w-full rounded-lg border border-line bg-panel-2 px-2.5 py-2",
  "font-mono text-[12px] text-ink",
  "focus:border-phosphor/50 focus:outline-none",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

const DEFAULT_STEP = 0.5;

// Friendly labels/icons for the common HVAC modes; unknown modes fall back to raw.
const MODE_META: Record<string, { label: string; icon: string }> = {
  off: { label: "Off", icon: "⏻" },
  cool: { label: "Cool", icon: "❄" },
  heat: { label: "Heat", icon: "☀" },
  auto: { label: "Auto", icon: "⇅" },
  dry: { label: "Dry", icon: "💧" },
  fan_only: { label: "Fan", icon: "🌀" },
  heat_cool: { label: "Heat/Cool", icon: "⇅" },
};

function modeMeta(mode: string) {
  return MODE_META[mode] ?? { label: mode, icon: "•" };
}

/**
 * Climate — pick an AC / thermostat (climate.* HA entity), see its current state,
 * and control target temperature + HVAC mode. Self-contained: loads the saved
 * entity + HA entity list, reads live state, and pushes changes through the API.
 */
export function ClimatePage() {
  const toasts = useToasts();

  const [entity, setEntity] = useState<string>("");
  const [haEnts, setHaEnts] = useState<HaEntity[]>([]);
  const [haConfigured, setHaConfigured] = useState(true);
  const [state, setState] = useState<ClimateState | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingEntity, setSavingEntity] = useState(false);
  const [busy, setBusy] = useState(false);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Read the live climate state for the chosen entity (no-op if none selected).
  const refreshState = useCallback(
    async (id: string) => {
      if (!id) {
        setState(null);
        return;
      }
      try {
        const s = await api.getClimateState(id);
        if (mounted.current) setState(s);
      } catch (err) {
        if (mounted.current) toasts.error(errMsg(err));
      }
    },
    [toasts],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [cfg, ents] = await Promise.all([
        api.getClimateConfig(),
        api.haEntities(["climate"]),
      ]);
      if (!mounted.current) return;
      setHaEnts(ents.entities ?? []);
      setHaConfigured(ents.ha_configured);
      setEntity(cfg.entity);
      if (cfg.entity && ents.ha_configured) await refreshState(cfg.entity);
    } catch (err) {
      if (mounted.current) toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [refreshState, toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const chooseEntity = useCallback(
    async (id: string) => {
      setEntity(id);
      setState(null);
      setSavingEntity(true);
      try {
        await api.setClimateConfig(id);
        if (id) await refreshState(id);
      } catch (err) {
        toasts.error(errMsg(err));
      } finally {
        if (mounted.current) setSavingEntity(false);
      }
    },
    [refreshState, toasts],
  );

  const setTemperature = useCallback(
    async (temperature: number) => {
      if (!entity) return;
      setBusy(true);
      try {
        await api.setClimate({ entity_id: entity, temperature });
        await refreshState(entity);
      } catch (err) {
        toasts.error(errMsg(err));
      } finally {
        if (mounted.current) setBusy(false);
      }
    },
    [entity, refreshState, toasts],
  );

  const setHvacMode = useCallback(
    async (hvac_mode: string) => {
      if (!entity) return;
      setBusy(true);
      try {
        await api.setClimate({ entity_id: entity, hvac_mode });
        await refreshState(entity);
      } catch (err) {
        toasts.error(errMsg(err));
      } finally {
        if (mounted.current) setBusy(false);
      }
    },
    [entity, refreshState, toasts],
  );

  const step = state?.target_temp_step || DEFAULT_STEP;
  const target = state?.temperature ?? null;

  const nudge = (dir: 1 | -1) => {
    if (target === null) return;
    let next = target + dir * step;
    if (state?.min_temp != null) next = Math.max(state.min_temp, next);
    if (state?.max_temp != null) next = Math.min(state.max_temp, next);
    // Avoid float drift like 21.499999.
    next = Math.round(next / step) * step;
    setTemperature(next);
  };

  return (
    <div className="space-y-5">
      <Panel eyebrow="hvac" title="Climate">
        <p className="font-mono text-[11px] leading-relaxed text-mute">
          Control your air conditioner / thermostat. Pick a{" "}
          <span className="text-soft">climate</span> entity from Home Assistant,
          then adjust the target temperature and mode.
        </p>
        {!haConfigured && (
          <p className="mt-3 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-[11px] leading-relaxed text-amber">
            Home Assistant isn't connected — set the HA URL + token in the add-on
            config to pick a climate entity.
          </p>
        )}
        <div className="mt-4">
          <div className="eyebrow mb-2">entity</div>
          <select
            value={entity}
            disabled={!haConfigured || savingEntity}
            onChange={(e) => chooseEntity(e.target.value)}
            className={selectCls}
          >
            <option value="">
              {haConfigured ? "— select a climate entity —" : "ha not connected"}
            </option>
            {haEnts.map((e) => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.name} · {e.entity_id}
              </option>
            ))}
          </select>
        </div>
      </Panel>

      {loading ? (
        <div className="h-56 animate-pulse rounded-2xl bg-line/40" />
      ) : entity && state ? (
        <ClimateControls
          state={state}
          busy={busy}
          onNudge={nudge}
          onMode={setHvacMode}
        />
      ) : entity ? (
        <Panel eyebrow="state" title="Loading…">
          <p className="font-mono text-[11px] text-mute">
            Reading the climate entity's state…
          </p>
        </Panel>
      ) : null}
    </div>
  );
}

function ClimateControls({
  state,
  busy,
  onNudge,
  onMode,
}: {
  state: ClimateState;
  busy: boolean;
  onNudge: (dir: 1 | -1) => void;
  onMode: (mode: string) => void;
}) {
  const current = state.current_temperature;
  const target = state.temperature;
  const modes = state.hvac_modes ?? [];
  const active = state.hvac_mode ?? state.state ?? "";

  return (
    <Panel
      eyebrow="state"
      title={modeMeta(active).label}
      right={
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {active || "—"}
        </span>
      }
    >
      <div className="space-y-6">
        {/* Current temp (large) + target */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="eyebrow mb-1">current</div>
            <div className="font-display text-5xl font-600 tabular-nums text-ink">
              {current != null ? `${current}°` : "—"}
            </div>
          </div>
          <div className="text-right">
            <div className="eyebrow mb-1">target</div>
            <div className="font-mono text-2xl tabular-nums text-phosphor">
              {target != null ? `${target}°` : "—"}
            </div>
          </div>
        </div>

        {/* Target temp −/+ */}
        <div>
          <div className="eyebrow mb-2">set target</div>
          <div className="flex items-center gap-3">
            <Button
              variant="subtle"
              disabled={busy || target == null}
              onClick={() => onNudge(-1)}
            >
              −
            </Button>
            <span className="min-w-[4ch] text-center font-mono text-xl tabular-nums text-ink">
              {target != null ? `${target}°` : "—"}
            </span>
            <Button
              variant="subtle"
              disabled={busy || target == null}
              onClick={() => onNudge(1)}
            >
              ＋
            </Button>
            <span className="font-mono text-[10px] text-mute">
              step {state.target_temp_step || DEFAULT_STEP}°
              {state.min_temp != null && state.max_temp != null
                ? ` · ${state.min_temp}–${state.max_temp}°`
                : ""}
            </span>
          </div>
        </div>

        {/* HVAC mode buttons */}
        {modes.length > 0 && (
          <div>
            <div className="eyebrow mb-2">mode</div>
            <div className="flex flex-wrap gap-2">
              {modes.map((m) => {
                const meta = modeMeta(m);
                const selected = m === active;
                return (
                  <Button
                    key={m}
                    variant={selected ? "primary" : "subtle"}
                    disabled={busy}
                    onClick={() => onMode(m)}
                  >
                    <span aria-hidden>{meta.icon}</span> {meta.label}
                  </Button>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
