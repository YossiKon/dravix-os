import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { ReactionRule } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, Toggle, cx, errMsg } from "./ui";
import { EXPRESSION_META } from "./expressions";

export function ReactionsPanel() {
  const toasts = useToasts();
  const [rules, setRules] = useState<ReactionRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [mode, setMode] = useState<"cards" | "json">("cards");

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
      const r = await api.reactions();
      if (mounted.current) setRules(r.reactions ?? []);
    } catch (err) {
      if (mounted.current) {
        setRules([]);
        toasts.error(errMsg(err));
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Persist the whole list (the API replaces the set).
  const save = useCallback(
    async (next: ReactionRule[]) => {
      setSaving(true);
      try {
        const res = await api.setReactions(next);
        if (mounted.current) setRules(res.reactions ?? next);
        toasts.ok("Reactions saved");
        return true;
      } catch (err) {
        toasts.error(errMsg(err));
        // Re-sync to authoritative state so the UI doesn't lie.
        refresh();
        return false;
      } finally {
        if (mounted.current) setSaving(false);
      }
    },
    [toasts, refresh],
  );

  function toggleRule(idx: number, enabled: boolean) {
    const next = rules.map((r, i) => (i === idx ? { ...r, enabled } : r));
    save(next);
  }

  function deleteRule(idx: number) {
    const next = rules.filter((_, i) => i !== idx);
    save(next);
  }

  function addRule(rule: ReactionRule) {
    save([...rules, rule]);
  }

  return (
    <Panel
      eyebrow="event → action"
      title="Reactions"
      right={
        <div className="flex items-center gap-1.5">
          <Button
            variant={mode === "cards" ? "primary" : "subtle"}
            className="px-2.5 py-1"
            onClick={() => setMode("cards")}
          >
            Cards
          </Button>
          <Button
            variant={mode === "json" ? "primary" : "subtle"}
            className="px-2.5 py-1"
            onClick={() => setMode("json")}
          >
            JSON
          </Button>
        </div>
      }
    >
      {loading && rules.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-xl bg-line/60" />
          ))}
        </div>
      ) : mode === "json" ? (
        <JsonEditor rules={rules} saving={saving} onSave={save} />
      ) : (
        <div className="space-y-5">
          <div className="space-y-2">
            {rules.length === 0 ? (
              <p className="font-mono text-[11px] text-mute">
                No reaction rules. Add one below.
              </p>
            ) : (
              rules.map((r, i) => (
                <RuleCard
                  key={`${r.name}-${i}`}
                  rule={r}
                  busy={saving}
                  onToggle={(en) => toggleRule(i, en)}
                  onDelete={() => deleteRule(i)}
                />
              ))
            )}
          </div>
          <AddRuleForm busy={saving} onAdd={addRule} />
        </div>
      )}
    </Panel>
  );
}

/* ── Rule card ──────────────────────────────────────────────────────────── */
function RuleCard({
  rule,
  busy,
  onToggle,
  onDelete,
}: {
  rule: ReactionRule;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
}) {
  const enabled = rule.enabled !== false;
  const actions = describeActions(rule);
  return (
    <div
      className={cx(
        "flex items-start gap-3 rounded-xl border px-3.5 py-3 transition-colors",
        enabled
          ? "border-line bg-panel-2/40"
          : "border-line bg-panel/50 opacity-60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-display text-sm font-600 text-ink">
            {rule.name || "(unnamed)"}
          </span>
          <span className="rounded border border-cyan/40 bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] tracking-wide text-cyan">
            on: {rule.on}
          </span>
          {rule.throttle_s != null && (
            <span className="rounded border border-line bg-panel-2 px-1.5 py-0.5 font-mono text-[10px] text-mute">
              throttle {rule.throttle_s}s
            </span>
          )}
        </div>
        <p className="mt-1 font-mono text-[11px] leading-relaxed text-soft">
          {actions.length > 0 ? (
            <span className="text-mute">→ </span>
          ) : (
            <span className="text-mute">no actions</span>
          )}
          {actions.join("  ·  ")}
        </p>
      </div>
      <Toggle
        on={enabled}
        disabled={busy}
        label={`Enable ${rule.name}`}
        onChange={onToggle}
      />
      <Button
        variant="danger"
        className="px-2.5 py-1.5"
        disabled={busy}
        onClick={onDelete}
        title="Delete rule"
      >
        ✕
      </Button>
    </div>
  );
}

function describeActions(r: ReactionRule): string[] {
  const out: string[] = [];
  if (r.say) out.push(`say "${truncate(r.say, 30)}"`);
  if (r.face) out.push(`face ${r.face}`);
  if (r.leds) out.push(`leds ${r.leds.color}`);
  if (r.frigate_show) out.push(`show ${r.frigate_show}`);
  if (r.activate_mode) out.push(`mode ${r.activate_mode}`);
  return out;
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/* ── Add-rule form ──────────────────────────────────────────────────────── */
function AddRuleForm({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (rule: ReactionRule) => void;
}) {
  const [name, setName] = useState("");
  const [on, setOn] = useState("");
  const [say, setSay] = useState("");
  const [face, setFace] = useState("");
  const expressions = Object.keys(EXPRESSION_META);

  const valid = name.trim() !== "" && on.trim() !== "";

  function submit() {
    if (!valid || busy) return;
    const rule: ReactionRule = {
      name: name.trim(),
      on: on.trim(),
      enabled: true,
      ...(say.trim() ? { say: say.trim() } : {}),
      ...(face ? { face } : {}),
    };
    onAdd(rule);
    setName("");
    setOn("");
    setSay("");
    setFace("");
  }

  const inputCls = cx(
    "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
    "font-body text-sm text-ink placeholder:text-mute/70",
    "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  );

  return (
    <div className="rounded-xl border border-line bg-panel-2/30 p-4">
      <div className="eyebrow mb-3 flex items-center gap-2">
        add rule
        <span className="h-px flex-1 bg-line/70" />
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <input
          className={inputCls}
          value={name}
          placeholder="name (e.g. greet_person)"
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={inputCls}
          value={on}
          placeholder="on event (e.g. frigate.person)"
          onChange={(e) => setOn(e.target.value)}
        />
        <input
          className={cx(inputCls, "sm:col-span-2")}
          value={say}
          placeholder="say (optional)"
          onChange={(e) => setSay(e.target.value)}
        />
        <label className="flex items-center gap-2 font-mono text-[11px] text-mute">
          face
          <select
            value={face}
            onChange={(e) => setFace(e.target.value)}
            className="rounded-lg border border-line bg-panel-2 px-2.5 py-1.5 font-mono text-[11px] text-ink focus:border-phosphor/50 focus:outline-none"
          >
            <option value="">none</option>
            {expressions.map((x) => (
              <option key={x} value={x}>
                {x}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center justify-end">
          <Button
            variant="primary"
            loading={busy}
            disabled={!valid}
            onClick={submit}
          >
            + Add rule
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ── Raw JSON editor (power-user / MVP) ─────────────────────────────────── */
function JsonEditor({
  rules,
  saving,
  onSave,
}: {
  rules: ReactionRule[];
  saving: boolean;
  onSave: (next: ReactionRule[]) => Promise<boolean>;
}) {
  const [text, setText] = useState(() => JSON.stringify(rules, null, 2));
  const [error, setError] = useState<string | null>(null);

  // Re-sync the editor when the upstream list changes (and not mid-edit).
  useEffect(() => {
    setText(JSON.stringify(rules, null, 2));
    setError(null);
  }, [rules]);

  function validateAndSave() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    if (!Array.isArray(parsed)) {
      setError("Expected a JSON array of rules.");
      return;
    }
    for (const r of parsed) {
      if (!r || typeof r !== "object" || typeof (r as ReactionRule).name !== "string" || typeof (r as ReactionRule).on !== "string") {
        setError('Each rule needs at least "name" and "on" strings.');
        return;
      }
    }
    setError(null);
    onSave(parsed as ReactionRule[]);
  }

  return (
    <div className="space-y-3">
      <textarea
        value={text}
        spellCheck={false}
        rows={14}
        onChange={(e) => setText(e.target.value)}
        className={cx(
          "scrollbar-thin w-full resize-y rounded-xl border border-line bg-void/60 px-3.5 py-3",
          "font-mono text-[12px] leading-relaxed text-ink",
          "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
          error && "border-fault/50",
        )}
      />
      {error && (
        <div className="rounded-lg border border-fault/30 bg-fault/5 px-3 py-2 font-mono text-[11px] text-fault">
          {error}
        </div>
      )}
      <div className="flex justify-end">
        <Button variant="primary" loading={saving} onClick={validateAndSave}>
          Validate &amp; Save
        </Button>
      </div>
    </div>
  );
}
