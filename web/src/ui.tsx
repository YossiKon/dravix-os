// Small shared UI pieces: card/section, toggle, and a toast channel.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

// ── toasts (module-level channel so any code can fire one) ────────────────────
export interface ToastMsg {
  id: number;
  text: string;
  kind: "ok" | "err";
}

let nextId = 1;
let push: ((t: ToastMsg) => void) | null = null;

export function toast(text: string, kind: "ok" | "err" = "ok"): void {
  push?.({ id: nextId++, text, kind });
}

export function toastErr(e: unknown): void {
  toast(e instanceof Error ? e.message : String(e), "err");
}

export function Toaster() {
  const [items, setItems] = useState<ToastMsg[]>([]);
  useEffect(() => {
    push = (t) => {
      setItems((cur) => [...cur, t]);
      setTimeout(() => setItems((cur) => cur.filter((x) => x.id !== t.id)), 3500);
    };
    return () => {
      push = null;
    };
  }, []);
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex flex-col items-center gap-2 px-4">
      {items.map((t) => (
        <div
          key={t.id}
          className={`animate-rise rounded-2xl border px-4 py-2.5 text-sm shadow-card ${
            t.kind === "ok" ? "border-teal/40 bg-card text-teal" : "border-red/40 bg-card text-red"
          }`}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}

// ── layout bits ───────────────────────────────────────────────────────────────
export function Section(props: { title: string; children: ReactNode; delay?: number }) {
  return (
    <section className="card animate-rise" style={{ animationDelay: `${props.delay ?? 0}ms` }}>
      <h2 className="card-title">{props.title}</h2>
      {props.children}
    </section>
  );
}

export function Toggle(props: { on: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button
      type="button"
      onClick={() => props.onChange(!props.on)}
      className="flex min-h-12 w-full items-center justify-between gap-3 rounded-2xl border border-line bg-card2 px-4 py-2 text-start"
    >
      <span className="text-ink">{props.label}</span>
      <span
        className={`relative h-7 w-12 shrink-0 rounded-full border transition ${
          props.on ? "border-teal/60 bg-teal/30" : "border-line-2 bg-bg"
        }`}
      >
        <span
          className={`absolute top-0.5 h-5.5 w-5.5 rounded-full transition-all ${
            props.on ? "end-0.5 bg-teal" : "start-0.5 bg-mute"
          }`}
          style={{ height: "22px", width: "22px" }}
        />
      </span>
    </button>
  );
}

export function Spinner() {
  return (
    <span className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-line-2 border-t-teal align-middle" />
  );
}
