import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Job } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, Toggle, cx, errMsg } from "./ui";
import { EXPRESSION_META } from "./expressions";

// 0=Mon .. 6=Sun, matching the backend convention.
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function SchedulePanel() {
  const toasts = useToasts();
  const [jobs, setJobs] = useState<Job[]>([]);
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
      const r = await api.schedule();
      if (mounted.current) setJobs(r.schedule ?? []);
    } catch (err) {
      if (mounted.current) {
        setJobs([]);
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
    async (next: Job[]) => {
      setSaving(true);
      try {
        const res = await api.setSchedule(next);
        if (mounted.current) setJobs(res.schedule ?? next);
        toasts.ok("Schedule saved");
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

  function toggleJob(idx: number, enabled: boolean) {
    save(jobs.map((j, i) => (i === idx ? { ...j, enabled } : j)));
  }

  function deleteJob(idx: number) {
    save(jobs.filter((_, i) => i !== idx));
  }

  function addJob(job: Job) {
    save([...jobs, job]);
  }

  return (
    <div className="space-y-5">
      <Panel
        eyebrow="daily jobs"
        title="Schedule"
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
        {loading && jobs.length === 0 ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-xl bg-line/60" />
            ))}
          </div>
        ) : mode === "json" ? (
          <JsonEditor jobs={jobs} saving={saving} onSave={save} />
        ) : (
          <div className="space-y-5">
            <div className="space-y-2">
              {jobs.length === 0 ? (
                <p className="font-mono text-[11px] text-mute">
                  No scheduled jobs. Add one below.
                </p>
              ) : (
                jobs.map((j, i) => (
                  <JobCard
                    key={`${j.name}-${i}`}
                    job={j}
                    busy={saving}
                    onToggle={(en) => toggleJob(i, en)}
                    onDelete={() => deleteJob(i)}
                  />
                ))
              )}
            </div>
            <AddJobForm busy={saving} onAdd={addJob} />
          </div>
        )}
      </Panel>

      <QuickTimer />
    </div>
  );
}

/* ── Job card ───────────────────────────────────────────────────────────── */
function JobCard({
  job,
  busy,
  onToggle,
  onDelete,
}: {
  job: Job;
  busy: boolean;
  onToggle: (enabled: boolean) => void;
  onDelete: () => void;
}) {
  const enabled = job.enabled !== false;
  const actions = describeAction(job);
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
            {job.name || "(unnamed)"}
          </span>
          <span className="rounded border border-cyan/40 bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] tracking-wide text-cyan">
            {job.at || "--:--"}
          </span>
          <span className="rounded border border-line bg-panel-2 px-1.5 py-0.5 font-mono text-[10px] text-mute">
            {describeDays(job.days)}
          </span>
        </div>
        <p className="mt-1 font-mono text-[11px] leading-relaxed text-soft">
          {actions.length > 0 ? (
            <span className="text-mute">→ </span>
          ) : (
            <span className="text-mute">no action</span>
          )}
          {actions.join("  ·  ")}
        </p>
      </div>
      <Toggle
        on={enabled}
        disabled={busy}
        label={`Enable ${job.name}`}
        onChange={onToggle}
      />
      <Button
        variant="danger"
        className="px-2.5 py-1.5"
        disabled={busy}
        onClick={onDelete}
        title="Delete job"
      >
        ✕
      </Button>
    </div>
  );
}

function describeAction(j: Job): string[] {
  const a = j.action ?? {};
  const out: string[] = [];
  if (a.say) out.push(`say "${truncate(a.say, 30)}"`);
  if (a.face) out.push(`face ${a.face}`);
  if (a.emote) out.push(`emote ${a.emote}`);
  if (a.activate_mode) out.push(`mode ${a.activate_mode}`);
  return out;
}

function describeDays(days?: number[]): string {
  if (!days || days.length === 0) return "every day";
  if (days.length === 7) return "every day";
  return [...days]
    .sort((a, b) => a - b)
    .map((d) => DAY_LABELS[d] ?? `?${d}`)
    .join(" ");
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

/* ── Add-job form ───────────────────────────────────────────────────────── */
function AddJobForm({
  busy,
  onAdd,
}: {
  busy: boolean;
  onAdd: (job: Job) => void;
}) {
  const [name, setName] = useState("");
  const [at, setAt] = useState("");
  const [days, setDays] = useState<number[]>([]);
  const [say, setSay] = useState("");
  const [face, setFace] = useState("");
  const [emote, setEmote] = useState("");
  const expressions = Object.keys(EXPRESSION_META);

  // Require a name and a valid HH:MM time.
  const valid = name.trim() !== "" && /^\d{1,2}:\d{2}$/.test(at.trim());

  function toggleDay(d: number) {
    setDays((cur) =>
      cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d],
    );
  }

  function submit() {
    if (!valid || busy) return;
    const action: Job["action"] = {
      ...(say.trim() ? { say: say.trim() } : {}),
      ...(face ? { face } : {}),
      ...(emote.trim() ? { emote: emote.trim() } : {}),
    };
    const job: Job = {
      name: name.trim(),
      at: at.trim(),
      enabled: true,
      action,
      ...(days.length > 0 ? { days: [...days].sort((a, b) => a - b) } : {}),
    };
    onAdd(job);
    setName("");
    setAt("");
    setDays([]);
    setSay("");
    setFace("");
    setEmote("");
  }

  const inputCls = cx(
    "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
    "font-body text-sm text-ink placeholder:text-mute/70",
    "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  );

  return (
    <div className="rounded-xl border border-line bg-panel-2/30 p-4">
      <div className="eyebrow mb-3 flex items-center gap-2">
        add job
        <span className="h-px flex-1 bg-line/70" />
      </div>
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        <input
          className={inputCls}
          value={name}
          placeholder="name (e.g. morning_greeting)"
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={inputCls}
          type="time"
          value={at}
          placeholder="HH:MM"
          onChange={(e) => setAt(e.target.value)}
        />
        <div className="sm:col-span-2">
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-mute">
            days (none = every day)
          </div>
          <div className="flex flex-wrap gap-1.5">
            {DAY_LABELS.map((label, d) => {
              const on = days.includes(d);
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => toggleDay(d)}
                  className={cx(
                    "rounded-lg border px-2.5 py-1.5 font-mono text-[11px] tracking-wide transition-all",
                    on
                      ? "border-phosphor/50 bg-phosphor/15 text-phosphor shadow-glow"
                      : "border-line bg-panel-2 text-soft hover:border-line-bright hover:text-ink",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
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
        <input
          className={inputCls}
          value={emote}
          placeholder="emote (optional)"
          onChange={(e) => setEmote(e.target.value)}
        />
        <div className="flex items-center justify-end sm:col-span-2">
          <Button
            variant="primary"
            loading={busy}
            disabled={!valid}
            onClick={submit}
          >
            + Add job
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ── Quick timer ────────────────────────────────────────────────────────── */
function QuickTimer() {
  const toasts = useToasts();
  const [minutes, setMinutes] = useState("5");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const mins = Number(minutes);
  const valid = Number.isFinite(mins) && mins > 0;

  async function submit() {
    if (!valid || busy) return;
    setBusy(true);
    try {
      const seconds = Math.round(mins * 60);
      const res = await api.setTimer(seconds, label.trim() || undefined);
      toasts.ok(
        `Timer set for ${mins}m${res.label ? ` · ${res.label}` : ""}`,
      );
      setLabel("");
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      setBusy(false);
    }
  }

  const inputCls = cx(
    "rounded-lg border border-line bg-void/60 px-3 py-2",
    "font-body text-sm text-ink placeholder:text-mute/70",
    "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  );

  return (
    <Panel eyebrow="one-shot" title="Quick Timer">
      <div className="flex flex-wrap items-end gap-2.5">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
            minutes
          </span>
          <input
            className={cx(inputCls, "w-24")}
            type="number"
            min={1}
            step={1}
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </label>
        <label className="flex min-w-[12rem] flex-1 flex-col gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
            label (optional)
          </span>
          <input
            className={cx(inputCls, "w-full")}
            value={label}
            placeholder="e.g. tea is ready"
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
          />
        </label>
        <Button
          variant="primary"
          loading={busy}
          disabled={!valid}
          onClick={submit}
        >
          ▸ Set timer
        </Button>
      </div>
    </Panel>
  );
}

/* ── Raw JSON editor (power-user / MVP) ─────────────────────────────────── */
function JsonEditor({
  jobs,
  saving,
  onSave,
}: {
  jobs: Job[];
  saving: boolean;
  onSave: (next: Job[]) => Promise<boolean>;
}) {
  const [text, setText] = useState(() => JSON.stringify(jobs, null, 2));
  const [error, setError] = useState<string | null>(null);

  // Re-sync the editor when the upstream list changes (and not mid-edit).
  useEffect(() => {
    setText(JSON.stringify(jobs, null, 2));
    setError(null);
  }, [jobs]);

  function validateAndSave() {
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid JSON");
      return;
    }
    if (!Array.isArray(parsed)) {
      setError("Expected a JSON array of jobs.");
      return;
    }
    for (const j of parsed) {
      if (
        !j ||
        typeof j !== "object" ||
        typeof (j as Job).name !== "string" ||
        typeof (j as Job).at !== "string"
      ) {
        setError('Each job needs at least "name" and "at" strings.');
        return;
      }
    }
    setError(null);
    onSave(parsed as Job[]);
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
