// מזגן — בחירת ישות climate ושליטה: טמפ׳ יעד + מצב פעולה.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { ClimateState, HAEntity } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { Section, Spinner, toastErr } from "../ui";

const MODE_HE: Record<string, string> = {
  off: "כבוי",
  cool: "קירור",
  heat: "חימום",
  heat_cool: "אוטומטי",
  auto: "אוטומטי",
  dry: "ייבוש",
  fan_only: "מאוורר",
};

export function ClimatePage(props: { entities: HAEntity[] }) {
  const [entity, setEntity] = useState("");
  const [st, setSt] = useState<ClimateState | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadedCfg, setLoadedCfg] = useState(false);

  useEffect(() => {
    apiGet<{ entity: string }>("/api/config/climate")
      .then((r) => {
        setEntity(r.entity);
        setLoadedCfg(true);
      })
      .catch(() => setLoadedCfg(true));
  }, []);

  const refresh = useCallback(async (ent: string) => {
    if (!ent) {
      setSt(null);
      return;
    }
    try {
      setSt(await apiGet<ClimateState>(`/api/climate/state?entity_id=${encodeURIComponent(ent)}`));
    } catch (e) {
      setSt(null);
      toastErr(e);
    }
  }, []);

  useEffect(() => {
    if (loadedCfg) void refresh(entity);
  }, [entity, loadedCfg, refresh]);

  // poll while visible so the current temperature stays fresh
  useEffect(() => {
    if (!entity) return;
    const t = setInterval(() => {
      if (document.visibilityState === "visible") void refresh(entity);
    }, 10000);
    return () => clearInterval(t);
  }, [entity, refresh]);

  async function choose(ent: string) {
    setEntity(ent);
    try {
      await apiSend("/api/config/climate", "PUT", { entity: ent });
    } catch (e) {
      toastErr(e);
    }
  }

  async function setTemp(next: number) {
    if (!entity) return;
    setBusy(true);
    try {
      await apiSend("/api/climate/set", "POST", { entity_id: entity, temperature: next });
      setSt((cur) => (cur ? { ...cur, temperature: next } : cur));
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  async function setMode(mode: string) {
    if (!entity) return;
    setBusy(true);
    try {
      await apiSend("/api/climate/set", "POST", { entity_id: entity, hvac_mode: mode });
      setSt((cur) => (cur ? { ...cur, state: mode } : cur));
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy(false);
    }
  }

  const step = st?.target_temp_step ?? 0.5;
  const target = st?.temperature ?? null;

  return (
    <div className="space-y-4">
      <Section title="איזה מזגן?">
        <EntityPicker
          entities={props.entities}
          domains={["climate"]}
          value={entity}
          onChange={(id) => void choose(id)}
          placeholder="בחר מזגן…"
        />
      </Section>

      {entity && st && (
        <Section title="שליטה" delay={70}>
          {/* current + target */}
          <div className="mb-4 flex items-center justify-around">
            <div className="text-center">
              <div className="text-sm text-mute">בבית עכשיו</div>
              <div className="font-display text-4xl">
                {st.current_temperature != null ? `${st.current_temperature}°` : "—"}
              </div>
            </div>
            <div className="text-center">
              <div className="text-sm text-mute">יעד</div>
              <div className="font-display text-4xl text-teal">{target != null ? `${target}°` : "—"}</div>
            </div>
          </div>
          {/* target +/- */}
          <div className="mb-4 grid grid-cols-2 gap-2">
            <button
              className="btn text-2xl"
              disabled={busy || target == null}
              onClick={() => target != null && void setTemp(Math.max(st.min_temp ?? 16, target - step))}
            >
              −
            </button>
            <button
              className="btn text-2xl"
              disabled={busy || target == null}
              onClick={() => target != null && void setTemp(Math.min(st.max_temp ?? 30, target + step))}
            >
              ＋
            </button>
          </div>
          {/* hvac modes */}
          <div className="flex flex-wrap gap-2">
            {(st.hvac_modes ?? []).map((m) => (
              <button
                key={m}
                className={`chip ${st.state === m ? "chip-on" : ""}`}
                disabled={busy}
                onClick={() => void setMode(m)}
              >
                {MODE_HE[m] ?? m}
              </button>
            ))}
            {busy && <Spinner />}
          </div>
        </Section>
      )}

      {entity && !st && (
        <div className="card animate-rise text-mute">טוען את מצב המזגן…</div>
      )}
      {!entity && loadedCfg && (
        <div className="card animate-rise text-mute">בחר מזגן מהרשימה כדי לשלוט בו מכאן ומכרטיסי הרובוט.</div>
      )}
    </div>
  );
}
