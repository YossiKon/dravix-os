// A searchable Home Assistant entity picker (big touch targets, works well on phones).
import { useMemo, useState } from "react";
import type { HAEntity } from "../api";

export function EntityPicker(props: {
  entities: HAEntity[];
  domains?: string[]; // limit to these domains (empty/undefined = all)
  value: string;
  onChange: (entityId: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");

  const pool = useMemo(() => {
    const doms = props.domains?.filter(Boolean) ?? [];
    let list = doms.length ? props.entities.filter((e) => doms.includes(e.domain)) : props.entities;
    const needle = q.trim().toLowerCase();
    if (needle) {
      list = list.filter(
        (e) => e.name.toLowerCase().includes(needle) || e.entity_id.toLowerCase().includes(needle),
      );
    }
    return list.slice(0, 80);
  }, [props.entities, props.domains, q]);

  const current = props.entities.find((e) => e.entity_id === props.value);

  return (
    <div className="relative">
      <button
        type="button"
        className="inp flex items-center justify-between gap-2 text-start"
        onClick={() => setOpen((v) => !v)}
      >
        {props.value ? (
          <span className="truncate">
            {current?.name ?? props.value}
            <span dir="ltr" className="ms-2 font-mono text-xs text-mute">
              {props.value}
            </span>
          </span>
        ) : (
          <span className="text-mute">{props.placeholder ?? "בחר ישות…"}</span>
        )}
        <span className="text-mute">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="absolute z-30 mt-2 w-full overflow-hidden rounded-2xl border border-line-2 bg-card shadow-card">
          <input
            autoFocus
            className="w-full border-b border-line bg-card2 px-4 py-3 text-ink outline-none placeholder:text-mute"
            placeholder="חיפוש…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="max-h-64 overflow-y-auto">
            {props.value && (
              <button
                type="button"
                className="block w-full px-4 py-3 text-start text-red"
                onClick={() => {
                  props.onChange("");
                  setOpen(false);
                }}
              >
                ✕ נקה בחירה
              </button>
            )}
            {pool.map((e) => (
              <button
                key={e.entity_id}
                type="button"
                className={`block w-full px-4 py-3 text-start transition hover:bg-card2 ${
                  e.entity_id === props.value ? "bg-teal/10 text-teal" : "text-ink"
                }`}
                onClick={() => {
                  props.onChange(e.entity_id);
                  setOpen(false);
                  setQ("");
                }}
              >
                <div className="truncate">{e.name}</div>
                <div dir="ltr" className="truncate text-start font-mono text-xs text-mute">
                  {e.entity_id}
                </div>
              </button>
            ))}
            {pool.length === 0 && <div className="px-4 py-3 text-mute">אין תוצאות</div>}
          </div>
        </div>
      )}
    </div>
  );
}
