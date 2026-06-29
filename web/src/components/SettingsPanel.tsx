import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { humanize } from "../lib/format";
import type { ConfigResponse, ModeInfo, Persona } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, Toggle, cx, errMsg } from "./ui";
import { EXPRESSION_META } from "./expressions";

const LOCAL_ONLY_HINT =
  "cloud providers refused — set DRAVIX_LOCAL_ONLY=false to allow";

export function SettingsPanel({
  modes,
  onModesChanged,
}: {
  modes: ModeInfo[];
  onModesChanged: () => void;
}) {
  const toasts = useToasts();
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

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
      const c = await api.config();
      if (mounted.current) setConfig(c);
    } catch (err) {
      if (mounted.current) toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const localOnly = config?.local_only ?? false;
  const cloud = new Set(config?.cloud_providers ?? []);

  async function pickProvider(provider: string | null) {
    setBusy("provider");
    try {
      const res = await api.setAiProvider(provider);
      if (res.error) toasts.error(res.error);
      else
        toasts.ok(
          res.ai_provider
            ? `AI provider → ${res.ai_provider}${res.ai_available ? "" : " (offline)"}`
            : "AI provider cleared",
        );
      refresh();
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  async function toggleMode(name: string, disabled: boolean) {
    setBusy(`mode:${name}`);
    try {
      await api.setModeDisabled(name, disabled);
      toasts.ok(`${humanize(name)} ${disabled ? "disabled" : "enabled"}`);
      onModesChanged();
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      <Panel
        eyebrow="configuration"
        title="AI Provider"
        right={
          localOnly && (
            <span
              title={LOCAL_ONLY_HINT}
              className="cursor-help rounded border border-amber/40 bg-amber/10 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-amber"
            >
              local-only
            </span>
          )
        }
      >
        {loading && !config ? (
          <div className="flex flex-wrap gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <span key={i} className="h-9 w-28 animate-pulse rounded-lg bg-line" />
            ))}
          </div>
        ) : !config ? (
          <p className="font-mono text-xs text-mute">Config unavailable.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2">
              {config.providers.length === 0 && (
                <p className="font-mono text-[11px] text-mute">
                  No providers registered.
                </p>
              )}
              {config.providers.map((p) => {
                const selected = config.ai_provider === p;
                const blocked = localOnly && cloud.has(p);
                return (
                  <button
                    key={p}
                    disabled={blocked || busy === "provider"}
                    title={
                      blocked
                        ? LOCAL_ONLY_HINT
                        : selected
                          ? "Active provider"
                          : `Switch to ${p}`
                    }
                    onClick={() => pickProvider(p)}
                    className={cx(
                      "rounded-lg border px-3.5 py-2 font-mono text-xs uppercase tracking-[0.08em] transition-all",
                      "disabled:cursor-not-allowed",
                      selected
                        ? "border-phosphor/50 bg-phosphor/15 text-phosphor shadow-glow"
                        : blocked
                          ? "border-line bg-panel/50 text-mute line-through decoration-mute/50 opacity-50"
                          : "border-line bg-panel-2 text-soft hover:border-line-bright hover:text-ink",
                    )}
                  >
                    {p}
                    {blocked && (
                      <span className="ml-1.5 text-[9px] text-amber no-underline">
                        cloud
                      </span>
                    )}
                  </button>
                );
              })}
              {config.ai_provider && (
                <Button
                  variant="ghost"
                  loading={busy === "provider"}
                  onClick={() => pickProvider(null)}
                >
                  Clear
                </Button>
              )}
            </div>
            <div className="mt-3 flex items-center gap-2 font-mono text-[11px] text-mute">
              <span
                className={cx(
                  "inline-block h-2 w-2 rounded-full",
                  config.ai_available ? "bg-phosphor" : "bg-mute",
                )}
              />
              {config.ai_provider
                ? `${config.ai_provider} · ${config.ai_available ? "available" : "offline"}`
                : "no provider selected"}
            </div>
          </>
        )}
      </Panel>

      <AnnounceBox />

      <PersonasBox />

      <Panel eyebrow="behaviors" title="Mode Availability">
        {modes.length === 0 ? (
          <p className="font-mono text-xs text-mute">No modes registered.</p>
        ) : (
          <div className="space-y-2">
            {modes.map((m) => {
              const disabled = m.disabled ?? false;
              return (
                <div
                  key={m.name}
                  className="flex items-center gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-display text-sm font-600 text-ink">
                      {humanize(m.name)}
                    </div>
                    {m.description && (
                      <p className="truncate font-mono text-[11px] text-mute">
                        {m.description}
                      </p>
                    )}
                  </div>
                  <span
                    className={cx(
                      "font-mono text-[10px] uppercase tracking-wider",
                      disabled ? "text-mute" : "text-phosphor",
                    )}
                  >
                    {disabled ? "disabled" : "enabled"}
                  </span>
                  <Toggle
                    on={!disabled}
                    disabled={busy === `mode:${m.name}`}
                    label={`Enable ${m.name}`}
                    onChange={(next) => toggleMode(m.name, !next)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </Panel>

      <Panel eyebrow="reference" title="Config Store">
        {!config ? (
          <p className="font-mono text-xs text-mute">—</p>
        ) : (
          <pre className="scrollbar-thin max-h-72 overflow-auto rounded-xl border border-line bg-void/60 p-3 font-mono text-[11px] leading-relaxed text-soft">
            {JSON.stringify(config.store, null, 2)}
          </pre>
        )}
      </Panel>
    </div>
  );
}

/* ── Announce (robot speaks with a face) ────────────────────────────────── */
function AnnounceBox() {
  const toasts = useToasts();
  const [text, setText] = useState("");
  const [expression, setExpression] = useState("");
  const [busy, setBusy] = useState(false);

  const expressions = Object.keys(EXPRESSION_META);

  async function submit() {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      await api.announce(t, expression || undefined);
      toasts.ok("Announced");
      setText("");
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel eyebrow="broadcast" title="Announce">
      <div className="flex flex-col gap-2">
        <textarea
          value={text}
          rows={2}
          placeholder="Announcement text — the robot speaks it with a face…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
          }}
          className={cx(
            "w-full resize-none rounded-xl border border-line bg-void/60 px-3.5 py-3",
            "font-body text-sm text-ink placeholder:text-mute/70",
            "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
          )}
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <label className="flex items-center gap-2 font-mono text-[11px] text-mute">
            face
            <select
              value={expression}
              onChange={(e) => setExpression(e.target.value)}
              className="rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 font-mono text-[11px] text-ink focus:border-phosphor/50 focus:outline-none"
            >
              <option value="">auto</option>
              {expressions.map((x) => (
                <option key={x} value={x}>
                  {x}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="primary"
            loading={busy}
            disabled={!text.trim()}
            onClick={submit}
          >
            ▸ Announce
          </Button>
        </div>
      </div>
    </Panel>
  );
}

/* ── Personas (pick active + add/edit) ──────────────────────────────────── */
const PERSONA_EXPRESSIONS = Object.keys(EXPRESSION_META);

function emptyDraft(): Persona {
  return { name: "", system_prompt: "", default_expression: "" };
}

function PersonasBox() {
  const toasts = useToasts();
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Persona>(emptyDraft);
  const [editingName, setEditingName] = useState<string | null>(null);

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
      const r = await api.personas();
      if (mounted.current) {
        setPersonas(r.personas ?? []);
        setActive(r.active ?? null);
      }
    } catch (err) {
      if (mounted.current) {
        setPersonas([]);
        toasts.error(errMsg(err));
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // POST /personas/active and surface any backend `error` as a toast.
  async function pickActive(name: string | null) {
    setBusy(true);
    try {
      const res = await api.setActivePersona(name);
      if (res.error) toasts.error(res.error);
      else
        toasts.ok(
          res.active ? `Persona → ${res.active}` : "Persona → Default",
        );
      if (mounted.current) setActive(res.active ?? null);
    } catch (err) {
      toasts.error(errMsg(err));
      refresh();
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  // PUT the whole persona list (the API replaces the set).
  async function savePersonas(next: Persona[]) {
    setBusy(true);
    try {
      const res = await api.setPersonas(next);
      if (mounted.current) setPersonas(res.personas ?? next);
      toasts.ok("Personas saved");
      return true;
    } catch (err) {
      toasts.error(errMsg(err));
      refresh();
      return false;
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  function startEdit(p: Persona) {
    setEditingName(p.name);
    setDraft({
      name: p.name,
      system_prompt: p.system_prompt,
      default_expression: p.default_expression ?? "",
      ...(p.voice ? { voice: p.voice } : {}),
    });
  }

  function cancelEdit() {
    setEditingName(null);
    setDraft(emptyDraft());
  }

  async function deletePersona(name: string) {
    const next = personas.filter((p) => p.name !== name);
    const ok = await savePersonas(next);
    if (ok && active === name) setActive(null);
    if (editingName === name) cancelEdit();
  }

  async function submitDraft() {
    const name = draft.name.trim();
    if (!name || busy) return;
    const entry: Persona = {
      name,
      system_prompt: draft.system_prompt,
      ...(draft.default_expression
        ? { default_expression: draft.default_expression }
        : {}),
      ...(draft.voice ? { voice: draft.voice } : {}),
    };
    // Replace by original name (rename-safe) or by matching new name; else add.
    const key = editingName ?? name;
    const exists = personas.some((p) => p.name === key);
    const next = exists
      ? personas.map((p) => (p.name === key ? entry : p))
      : [...personas, entry];
    const ok = await savePersonas(next);
    if (ok) cancelEdit();
  }

  const inputCls = cx(
    "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
    "font-body text-sm text-ink placeholder:text-mute/70",
    "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  );

  return (
    <Panel
      eyebrow="character"
      title="Personas"
      right={
        <label className="flex items-center gap-2 font-mono text-[11px] text-mute">
          active
          <select
            value={active ?? ""}
            disabled={busy || loading}
            onChange={(e) => pickActive(e.target.value || null)}
            className="rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 font-mono text-[11px] text-ink focus:border-phosphor/50 focus:outline-none disabled:opacity-50"
          >
            <option value="">Default</option>
            {personas.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      }
    >
      {loading && personas.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-xl bg-line/60" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-2">
            {personas.length === 0 ? (
              <p className="font-mono text-[11px] text-mute">
                No personas yet. Default uses the built-in system prompt.
              </p>
            ) : (
              personas.map((p) => {
                const isActive = active === p.name;
                return (
                  <div
                    key={p.name}
                    className={cx(
                      "flex items-start gap-3 rounded-xl border px-3.5 py-2.5",
                      isActive
                        ? "border-phosphor/40 bg-phosphor/5"
                        : "border-line bg-panel-2/40",
                    )}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate font-display text-sm font-600 text-ink">
                          {p.name}
                        </span>
                        {isActive && (
                          <span className="rounded border border-phosphor/40 bg-phosphor/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-phosphor">
                            active
                          </span>
                        )}
                        {p.default_expression && (
                          <span className="rounded border border-amber/40 bg-amber/10 px-1.5 py-0.5 font-mono text-[10px] text-amber">
                            {p.default_expression}
                          </span>
                        )}
                      </div>
                      <p className="mt-1 line-clamp-2 font-mono text-[11px] leading-relaxed text-soft">
                        {p.system_prompt || (
                          <span className="text-mute">(no system prompt)</span>
                        )}
                      </p>
                    </div>
                    <Button
                      variant="subtle"
                      className="px-2.5 py-1.5"
                      disabled={busy}
                      onClick={() => startEdit(p)}
                      title="Edit persona"
                    >
                      Edit
                    </Button>
                    <Button
                      variant="danger"
                      className="px-2.5 py-1.5"
                      disabled={busy}
                      onClick={() => deletePersona(p.name)}
                      title="Delete persona"
                    >
                      ✕
                    </Button>
                  </div>
                );
              })
            )}
          </div>

          <div className="rounded-xl border border-line bg-panel-2/30 p-4">
            <div className="eyebrow mb-3 flex items-center gap-2">
              {editingName ? `edit · ${editingName}` : "add persona"}
              <span className="h-px flex-1 bg-line/70" />
            </div>
            <div className="space-y-2.5">
              <input
                className={inputCls}
                value={draft.name}
                placeholder="name (e.g. Captain)"
                onChange={(e) =>
                  setDraft((d) => ({ ...d, name: e.target.value }))
                }
              />
              <textarea
                value={draft.system_prompt}
                rows={4}
                placeholder="system prompt — how the robot should behave…"
                onChange={(e) =>
                  setDraft((d) => ({ ...d, system_prompt: e.target.value }))
                }
                className={cx(
                  "scrollbar-thin w-full resize-y rounded-xl border border-line bg-void/60 px-3.5 py-3",
                  "font-body text-sm text-ink placeholder:text-mute/70",
                  "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
                )}
              />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="flex items-center gap-2 font-mono text-[11px] text-mute">
                  default face
                  <select
                    value={draft.default_expression ?? ""}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        default_expression: e.target.value,
                      }))
                    }
                    className="rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 font-mono text-[11px] text-ink focus:border-phosphor/50 focus:outline-none"
                  >
                    <option value="">none</option>
                    {PERSONA_EXPRESSIONS.map((x) => (
                      <option key={x} value={x}>
                        {x}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="flex items-center gap-2">
                  {editingName && (
                    <Button variant="ghost" disabled={busy} onClick={cancelEdit}>
                      Cancel
                    </Button>
                  )}
                  <Button
                    variant="primary"
                    loading={busy}
                    disabled={!draft.name.trim()}
                    onClick={submitDraft}
                  >
                    {editingName ? "Save persona" : "+ Add persona"}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
