// Screens — a drag-and-drop editor for the robot's 3 cards. Drag entities between cards and
// reorder rows (or use the ▲▼ buttons on touch); the Mushroom-style preview mirrors what the
// robot shows (up to 4 rows/card, a colour chip by domain). Saves to /api/screens.
import { useEffect, useRef, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { HAEntity, ScreenCard } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

const MAX_PER_CARD = 4;

// Domain → chip colour, mirroring the robot's Mushroom chips.
function chipColor(entityId: string): string {
  const d = entityId.split(".")[0];
  if (d === "light") return "#f5a623";
  if (["switch", "fan", "input_boolean", "automation", "script", "scene", "siren"].includes(d)) return "#4caf50";
  if (["sensor", "binary_sensor"].includes(d)) return "#4a90d9";
  if (d === "climate") return "#e67e22";
  if (["cover", "lock"].includes(d)) return "#9b59b6";
  if (d === "media_player") return "#e91e63";
  return "#8b96a4";
}

export function ScreensPage(props: { entities: HAEntity[] }) {
  const { tr } = useI18n();
  const [cards, setCards] = useState<ScreenCard[]>([
    { title: "", entities: [] },
    { title: "", entities: [] },
    { title: "", entities: [] },
  ]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);
  const dragSrc = useRef<{ card: number; idx: number } | null>(null);
  const [overCard, setOverCard] = useState<number | null>(null);

  useEffect(() => {
    apiGet<{ screens: ScreenCard[] }>("/api/screens")
      .then((r) => {
        const base: ScreenCard[] = [
          { title: "", entities: [] },
          { title: "", entities: [] },
          { title: "", entities: [] },
        ];
        r.screens.slice(0, 3).forEach((c, i) => {
          base[i] = { title: c.title ?? "", entities: c.entities ?? [] };
        });
        setCards(base);
        setLoaded(true);
      })
      .catch(toastErr);
  }, []);

  const nameOf = (id: string) => props.entities.find((e) => e.entity_id === id)?.name ?? id;

  function patch(i: number, next: Partial<ScreenCard>) {
    setCards((cur) => cur.map((c, j) => (j === i ? { ...c, ...next } : c)));
  }

  // Move the dragged entity into card `toCard` at `toIdx` (null = append).
  function move(toCard: number, toIdx: number | null) {
    const src = dragSrc.current;
    dragSrc.current = null;
    setOverCard(null);
    if (!src) return;
    setCards((cur) => {
      const next = cur.map((c) => ({ ...c, entities: [...c.entities] }));
      const id = next[src.card].entities[src.idx];
      if (id === undefined) return cur;
      if (src.card !== toCard && next[toCard].entities.length >= MAX_PER_CARD) return cur; // target full
      next[src.card].entities.splice(src.idx, 1);
      let at = toIdx === null ? next[toCard].entities.length : toIdx;
      if (src.card === toCard && toIdx !== null && toIdx > src.idx) at -= 1; // removal shifted indices
      next[toCard].entities.splice(at, 0, id);
      return next;
    });
  }

  // Touch-friendly reorder within a card.
  function bump(card: number, idx: number, dir: -1 | 1) {
    setCards((cur) =>
      cur.map((c, j) => {
        if (j !== card) return c;
        const es = [...c.entities];
        const ni = idx + dir;
        if (ni < 0 || ni >= es.length) return c;
        [es[idx], es[ni]] = [es[ni], es[idx]];
        return { ...c, entities: es };
      }),
    );
  }

  async function save() {
    setSaving(true);
    try {
      await apiSend("/api/screens", "PUT", { screens: cards });
      toast(tr("נשמר — הכרטיסים יתעדכנו על הרובוט", "Saved — the cards update on the robot shortly"));
    } catch (e) {
      toastErr(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-mute">
        {tr(
          `גרור ישויות בין הכרטיסים וסדר את השורות (או ▲▼ במגע) — תצוגה חיה של מסך הרובוט, עד ${MAX_PER_CARD} לכרטיס. מחליקים ימין/שמאל על הרובוט לעבור בין הכרטיסים; נגיעה בשורה מפעילה/מכבה.`,
          `Drag entities between cards and reorder the rows (or ▲▼ on touch) — a live preview of the robot's screen, up to ${MAX_PER_CARD} per card. Swipe left/right on the robot to switch cards; a tap on a row toggles it.`,
        )}
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        {cards.map((card, i) => (
          <div
            key={i}
            onDragOver={(e) => {
              e.preventDefault();
              setOverCard(i);
            }}
            onDragLeave={() => setOverCard((c) => (c === i ? null : c))}
            onDrop={() => move(i, null)}
            className={`rounded-2xl border p-2 transition ${
              overCard === i ? "border-teal" : "border-line"
            } bg-black/30`}
          >
            <input
              className="mb-2 w-full rounded-lg bg-card2 px-2 py-1 text-center text-sm font-semibold text-teal outline-none"
              placeholder={tr(`כרטיס ${i + 1}`, `Card ${i + 1}`)}
              value={card.title}
              onChange={(e) => patch(i, { title: e.target.value })}
            />
            <div className="min-h-[3rem] space-y-1.5">
              {card.entities.map((id, idx) => (
                <div
                  key={id}
                  draggable
                  onDragStart={() => (dragSrc.current = { card: i, idx })}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.stopPropagation();
                    move(i, idx);
                  }}
                  className="flex cursor-grab items-center gap-2 rounded-xl bg-card2 px-2 py-1.5 active:cursor-grabbing"
                >
                  <span
                    className="h-6 w-6 shrink-0 rounded-full"
                    style={{ background: chipColor(id) }}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 truncate text-xs">{nameOf(id)}</span>
                  <button type="button" className="shrink-0 px-1 text-mute hover:text-teal disabled:opacity-30" disabled={idx === 0} onClick={() => bump(i, idx, -1)} aria-label="up">▲</button>
                  <button type="button" className="shrink-0 px-1 text-mute hover:text-teal disabled:opacity-30" disabled={idx === card.entities.length - 1} onClick={() => bump(i, idx, 1)} aria-label="down">▼</button>
                  <button
                    type="button"
                    className="shrink-0 px-1 text-mute hover:text-red"
                    onClick={() => patch(i, { entities: card.entities.filter((x) => x !== id) })}
                    aria-label={tr("הסר", "Remove")}
                  >
                    ✕
                  </button>
                </div>
              ))}
              {card.entities.length === 0 && (
                <div className="rounded-xl border border-dashed border-line py-4 text-center text-xs text-mute">
                  {tr("גרור לכאן / הוסף למטה", "Drop here / add below")}
                </div>
              )}
            </div>
            {card.entities.length < MAX_PER_CARD && (
              <div className="mt-2">
                <EntityPicker
                  entities={props.entities}
                  value=""
                  placeholder={tr("＋ הוסף…", "＋ Add…")}
                  onChange={(id) => {
                    if (id && !card.entities.includes(id)) patch(i, { entities: [...card.entities, id] });
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </div>

      <button className="btn btn-primary w-full" disabled={!loaded || saving} onClick={() => void save()}>
        {saving ? tr("שומר…", "Saving…") : tr("💾 שמור", "💾 Save cards")}
      </button>
    </div>
  );
}
