import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Memory, Routine } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { Button, Panel, cx, errMsg } from "./ui";

const inputCls = cx(
  "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
  "font-body text-sm text-ink placeholder:text-mute/70",
  "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
);

export function MemoryPanel() {
  return (
    <div className="space-y-5">
      <FactsPanel />
      <RoutinesPanel />
    </div>
  );
}

/* ── Facts ──────────────────────────────────────────────────────────────── */
function FactsPanel() {
  const toasts = useToasts();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");

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
      const r = await api.memory();
      if (mounted.current) setMemories(r.memories ?? []);
    } catch (err) {
      if (mounted.current) {
        setMemories([]);
        toasts.error(errMsg(err));
      }
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function add() {
    const value = text.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      const created = await api.addMemory(value);
      if (mounted.current) {
        setMemories((cur) => [...cur, created]);
        setText("");
      }
      toasts.ok("Memory added");
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await api.deleteMemory(id);
      if (mounted.current) {
        setMemories((cur) => cur.filter((m) => m.id !== id));
      }
      toasts.ok("Memory removed");
    } catch (err) {
      toasts.error(errMsg(err));
      refresh();
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  return (
    <Panel eyebrow="facts" title="Memory">
      {loading && memories.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-11 animate-pulse rounded-xl bg-line/60" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="space-y-2">
            {(memories ?? []).length === 0 ? (
              <p className="font-mono text-[11px] text-mute">
                Nothing remembered yet. Add a fact below.
              </p>
            ) : (
              memories.map((m) => (
                <div
                  key={m.id}
                  className="flex items-start gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5"
                >
                  <span className="mt-0.5 select-none font-mono text-[11px] text-mute">
                    ●
                  </span>
                  <p className="min-w-0 flex-1 break-words font-body text-sm text-ink">
                    {m.text}
                  </p>
                  <Button
                    variant="danger"
                    className="px-2.5 py-1.5"
                    disabled={busy}
                    onClick={() => remove(m.id)}
                    title="Forget this"
                  >
                    ✕
                  </Button>
                </div>
              ))
            )}
          </div>

          <div className="rounded-xl border border-line bg-panel-2/30 p-4">
            <div className="eyebrow mb-3 flex items-center gap-2">
              add memory
              <span className="h-px flex-1 bg-line/70" />
            </div>
            <div className="flex flex-wrap items-center gap-2.5">
              <input
                className={cx(inputCls, "min-w-[12rem] flex-1")}
                value={text}
                placeholder="e.g. my favourite colour is teal"
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") add();
                }}
              />
              <Button
                variant="primary"
                loading={busy}
                disabled={text.trim() === ""}
                onClick={add}
              >
                + Add
              </Button>
            </div>
            <p className="mt-2 font-mono text-[10px] tracking-wide text-mute">
              Or tell it in chat: "remember that …".
            </p>
          </div>
        </div>
      )}
    </Panel>
  );
}

/* ── Routines ───────────────────────────────────────────────────────────── */
function RoutinesPanel() {
  const toasts = useToasts();
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState<string | null>(null);

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
      const r = await api.routines();
      if (mounted.current) setRoutines(r.routines ?? []);
    } catch (err) {
      if (mounted.current) {
        setRoutines([]);
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
    async (next: Routine[]) => {
      setSaving(true);
      try {
        const res = await api.setRoutines(next);
        if (mounted.current) setRoutines(res.routines ?? next);
        toasts.ok("Routines saved");
        return true;
      } catch (err) {
        toasts.error(errMsg(err));
        refresh();
        return false;
      } finally {
        if (mounted.current) setSaving(false);
      }
    },
    [toasts, refresh],
  );

  function deleteRoutine(idx: number) {
    save(routines.filter((_, i) => i !== idx));
  }

  function addRoutine(routine: Routine): Promise<boolean> {
    return save([...routines, routine]);
  }

  async function run(name: string) {
    setRunning(name);
    try {
      await api.runRoutine(name);
      toasts.ok(`Running "${name}"`);
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setRunning(null);
    }
  }

  const existingNames = new Set(routines.map((r) => r.name));

  return (
    <Panel eyebrow="action macros" title="Routines">
      {loading && routines.length === 0 ? (
        <div className="space-y-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <div key={i} className="h-14 animate-pulse rounded-xl bg-line/60" />
          ))}
        </div>
      ) : (
        <div className="space-y-5">
          <div className="space-y-2">
            {(routines ?? []).length === 0 ? (
              <p className="font-mono text-[11px] text-mute">
                No routines yet. Add one below.
              </p>
            ) : (
              routines.map((r, i) => (
                <div
                  key={`${r.name}-${i}`}
                  className="flex items-center gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-3"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-display text-sm font-600 text-ink">
                        {r.name || "(unnamed)"}
                      </span>
                      <span className="rounded border border-cyan/40 bg-cyan/10 px-1.5 py-0.5 font-mono text-[10px] tracking-wide text-cyan">
                        {(r.steps ?? []).length} step
                        {(r.steps ?? []).length === 1 ? "" : "s"}
                      </span>
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    className="px-2.5 py-1.5"
                    loading={running === r.name}
                    disabled={
                      saving || (running !== null && running !== r.name)
                    }
                    onClick={() => run(r.name)}
                    title={`Run ${r.name}`}
                  >
                    ▸ Run
                  </Button>
                  <Button
                    variant="danger"
                    className="px-2.5 py-1.5"
                    disabled={saving || running !== null}
                    onClick={() => deleteRoutine(i)}
                    title="Delete routine"
                  >
                    ✕
                  </Button>
                </div>
              ))
            )}
          </div>

          <AddRoutineForm
            busy={saving}
            existingNames={existingNames}
            onAdd={addRoutine}
          />
        </div>
      )}
    </Panel>
  );
}

const STEP_PLACEHOLDER = `[
  { "face": "happy" },
  { "leds": { "color": "#00ffaa", "brightness": 0.8 } },
  { "say": "Good morning!" },
  { "wait": 1 },
  { "emote": "wave" }
]`;

function AddRoutineForm({
  busy,
  existingNames,
  onAdd,
}: {
  busy: boolean;
  existingNames: Set<string>;
  onAdd: (routine: Routine) => Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [stepsText, setStepsText] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (busy) return;
    const trimmed = name.trim();
    if (trimmed === "") {
      setError("A routine needs a name.");
      return;
    }
    if (existingNames.has(trimmed)) {
      setError(`A routine named "${trimmed}" already exists.`);
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(stepsText);
    } catch (e) {
      setError(e instanceof Error ? `Invalid JSON: ${e.message}` : "Invalid JSON");
      return;
    }
    if (!Array.isArray(parsed)) {
      setError("Steps must be a JSON array.");
      return;
    }
    for (const s of parsed) {
      if (!s || typeof s !== "object" || Array.isArray(s)) {
        setError("Each step must be a JSON object.");
        return;
      }
    }

    setError(null);
    const ok = await onAdd({
      name: trimmed,
      steps: parsed as Routine["steps"],
    });
    if (ok) {
      setName("");
      setStepsText("");
    }
  }

  return (
    <div className="rounded-xl border border-line bg-panel-2/30 p-4">
      <div className="eyebrow mb-3 flex items-center gap-2">
        add routine
        <span className="h-px flex-1 bg-line/70" />
      </div>
      <div className="space-y-2.5">
        <input
          className={inputCls}
          value={name}
          placeholder="name (e.g. wake_up)"
          onChange={(e) => setName(e.target.value)}
        />
        <div>
          <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-mute">
            steps (JSON array)
          </div>
          <textarea
            value={stepsText}
            spellCheck={false}
            rows={10}
            placeholder={STEP_PLACEHOLDER}
            onChange={(e) => setStepsText(e.target.value)}
            className={cx(
              "scrollbar-thin w-full resize-y rounded-xl border border-line bg-void/60 px-3.5 py-3",
              "font-mono text-[12px] leading-relaxed text-ink placeholder:text-mute/60",
              "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
              error && "border-fault/50",
            )}
          />
        </div>
        {error && (
          <div className="rounded-lg border border-fault/30 bg-fault/5 px-3 py-2 font-mono text-[11px] text-fault">
            {error}
          </div>
        )}
        <div className="flex justify-end">
          <Button
            variant="primary"
            loading={busy}
            disabled={name.trim() === "" || stepsText.trim() === ""}
            onClick={submit}
          >
            + Add routine
          </Button>
        </div>
      </div>
    </div>
  );
}
