// Screens — a free drag-and-drop layout editor for the robot's 3 cards. Each card is a live
// 320×240 preview; drag the Mushroom-style entity cards to ANY position (pointer events, so it
// works on touch too). Positions are saved as a per-entity {x,y} layout and the firmware places
// each row exactly there. Up to 4 entities/card. Saves to /api/screens.
import { useRef, useState, useEffect } from "react";
import { apiGet, apiSend } from "../api";
import type { HAEntity } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

const MAX_PER_CARD = 4;
const SCREEN_W = 320;
const SCREEN_H = 240;
const CARD_W = 150; // a positioned row card, in robot pixels
const CARD_H = 46;

type Card = { title: string; entities: string[]; layout?: Record<string, [number, number]> };

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

// Snap to a fixed 2-col × 4-row grid so cards can NEVER sit on top of each other.
const GRID_SLOTS: [number, number][] = [
  [8, 8], [162, 8], [8, 58], [162, 58], [8, 108], [162, 108], [8, 158], [162, 158],
];
const nearestSlot = (x: number, y: number): [number, number] =>
  GRID_SLOTS.reduce((best, s) =>
    Math.hypot(s[0] - x, s[1] - y) < Math.hypot(best[0] - x, best[1] - y) ? s : best,
  );
const nearestFreeSlot = (x: number, y: number, taken: Set<string>): [number, number] => {
  const sorted = [...GRID_SLOTS].sort(
    (a, b) => Math.hypot(a[0] - x, a[1] - y) - Math.hypot(b[0] - x, b[1] - y),
  );
  return sorted.find((s) => !taken.has(`${s[0]},${s[1]}`)) ?? sorted[0];
};
const posOf = (card: Card, id: string, idx: number): [number, number] =>
  card.layout?.[id] ?? GRID_SLOTS[idx] ?? [8, 8];

function CardCanvas(props: {
  card: Card;
  nameOf: (id: string) => string;
  onMove: (id: string, x: number, y: number) => void;
  onRemove: (id: string) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ id: string; offX: number; offY: number } | null>(null);

  const robotXY = (clientX: number, clientY: number) => {
    const r = ref.current!.getBoundingClientRect();
    const scale = r.width / SCREEN_W;
    return { x: (clientX - r.left) / scale, y: (clientY - r.top) / scale };
  };

  function down(e: React.PointerEvent, id: string, x: number, y: number) {
    const p = robotXY(e.clientX, e.clientY);
    drag.current = { id, offX: p.x - x, offY: p.y - y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function moveEvt(e: React.PointerEvent) {
    if (!drag.current) return;
    const p = robotXY(e.clientX, e.clientY);
    const rawX = p.x - drag.current.offX;
    const rawY = p.y - drag.current.offY;
    const dragId = drag.current.id;
    // slots the OTHER cards occupy → snap the dragged one to the nearest FREE slot (never overlap)
    const taken = new Set(
      props.card.entities
        .map((eid, i) => [eid, posOf(props.card, eid, i)] as const)
        .filter(([eid]) => eid !== dragId)
        .map(([, pos]) => nearestSlot(pos[0], pos[1]).join(",")),
    );
    const [sx, sy] = nearestFreeSlot(rawX, rawY, taken);
    props.onMove(dragId, sx, sy);
  }

  return (
    <div
      ref={ref}
      onPointerMove={moveEvt}
      onPointerUp={() => (drag.current = null)}
      className="relative w-full overflow-hidden rounded-xl border border-line"
      style={{ aspectRatio: `${SCREEN_W} / ${SCREEN_H}`, background: "#05080b" }}
    >
      {props.card.entities.map((id, idx) => {
        const [x, y] = posOf(props.card, id, idx);
        return (
          <div
            key={id}
            onPointerDown={(e) => down(e, id, x, y)}
            className="absolute flex touch-none items-center gap-1.5 rounded-lg px-1.5"
            style={{
              left: `${(x / SCREEN_W) * 100}%`,
              top: `${(y / SCREEN_H) * 100}%`,
              width: `${(CARD_W / SCREEN_W) * 100}%`,
              height: `${(CARD_H / SCREEN_H) * 100}%`,
              background: "#121821",
              cursor: "grab",
            }}
          >
            <span className="aspect-square h-[55%] shrink-0 rounded-full" style={{ background: chipColor(id) }} aria-hidden />
            <span className="min-w-0 flex-1 truncate text-[10px] leading-tight text-white">{props.nameOf(id)}</span>
            <button
              type="button"
              className="shrink-0 text-[10px] text-mute hover:text-red"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => props.onRemove(id)}
              aria-label="remove"
            >
              ✕
            </button>
          </div>
        );
      })}
      {props.card.entities.length === 0 && (
        <span className="absolute inset-0 flex items-center justify-center text-xs text-mute">
          320 × 240
        </span>
      )}
    </div>
  );
}

export function ScreensPage(props: { entities: HAEntity[] }) {
  const { tr } = useI18n();
  const [cards, setCards] = useState<Card[]>([
    { title: "", entities: [], layout: {} },
    { title: "", entities: [], layout: {} },
    { title: "", entities: [], layout: {} },
  ]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiGet<{ screens: Card[] }>("/api/screens")
      .then((r) => {
        const base: Card[] = [
          { title: "", entities: [], layout: {} },
          { title: "", entities: [], layout: {} },
          { title: "", entities: [], layout: {} },
        ];
        r.screens.slice(0, 3).forEach((c, i) => {
          base[i] = { title: c.title ?? "", entities: c.entities ?? [], layout: c.layout ?? {} };
        });
        setCards(base);
        setLoaded(true);
      })
      .catch(toastErr);
  }, []);

  const nameOf = (id: string) => props.entities.find((e) => e.entity_id === id)?.name ?? id;
  const patch = (i: number, next: Partial<Card>) =>
    setCards((cur) => cur.map((c, j) => (j === i ? { ...c, ...next } : c)));

  const moveEntity = (i: number, id: string, x: number, y: number) =>
    setCards((cur) => cur.map((c, j) => (j === i ? { ...c, layout: { ...c.layout, [id]: [x, y] } } : c)));

  const removeEntity = (i: number, id: string) =>
    setCards((cur) =>
      cur.map((c, j) => {
        if (j !== i) return c;
        const layout = { ...c.layout };
        delete layout[id];
        return { ...c, entities: c.entities.filter((x) => x !== id), layout };
      }),
    );

  const addEntity = (i: number, id: string) =>
    setCards((cur) =>
      cur.map((c, j) => {
        if (j !== i || c.entities.includes(id) || c.entities.length >= MAX_PER_CARD) return c;
        const taken = new Set(c.entities.map((e, k) => nearestSlot(...posOf(c, e, k)).join(",")));
        const [nx, ny] = nearestFreeSlot(8, 8, taken);
        return { ...c, entities: [...c.entities, id], layout: { ...c.layout, [id]: [nx, ny] } };
      }),
    );

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
          `כל כרטיס הוא preview של מסך הרובוט — גרור את הישויות לסידור (הן ננעלות לרשת ולא נערמות אחת על השנייה, עד ${MAX_PER_CARD} לכרטיס). מחליקים ימין/שמאל על הרובוט לעבור בין הכרטיסים; נגיעה בישות מפעילה/מכבה.`,
          `Each card is a live preview of the robot's screen — drag the entities to arrange them (they snap to a grid and never overlap, up to ${MAX_PER_CARD} per card). Swipe left/right on the robot to switch cards; a tap on an entity toggles it.`,
        )}
      </p>

      {cards.map((card, i) => (
        <div key={i} className="space-y-2 rounded-2xl border border-line bg-black/20 p-2">
          <input
            className="w-full rounded-lg bg-card2 px-2 py-1 text-center text-sm font-semibold text-teal outline-none"
            placeholder={tr(`כרטיס ${i + 1}`, `Card ${i + 1}`)}
            value={card.title}
            onChange={(e) => patch(i, { title: e.target.value })}
          />
          <CardCanvas
            card={card}
            nameOf={nameOf}
            onMove={(id, x, y) => moveEntity(i, id, x, y)}
            onRemove={(id) => removeEntity(i, id)}
          />
          {card.entities.length < MAX_PER_CARD && (
            <EntityPicker
              entities={props.entities}
              value=""
              placeholder={tr("＋ הוסף ישות…", "＋ Add entity…")}
              onChange={(id) => id && addEntity(i, id)}
            />
          )}
        </div>
      ))}

      <button className="btn btn-primary w-full" disabled={!loaded || saving} onClick={() => void save()}>
        {saving ? tr("שומר…", "Saving…") : tr("💾 שמור פריסה", "💾 Save layout")}
      </button>
    </div>
  );
}
