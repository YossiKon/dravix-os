import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useToasts } from "../hooks/useToasts";
import type { HaEntity, ScreenCard } from "../lib/types";
import { Button, Chip, Panel, cx, errMsg } from "../components/ui";

const CARD_COUNT = 3;

const inputCls = cx(
  "w-full rounded-lg border border-line bg-void/60 px-3 py-2",
  "font-mono text-sm text-ink placeholder:text-mute/70",
  "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

const selectCls = cx(
  "w-full rounded-lg border border-line bg-panel-2 px-2.5 py-2",
  "font-mono text-[12px] text-ink",
  "focus:border-phosphor/50 focus:outline-none",
  "disabled:cursor-not-allowed disabled:opacity-40",
);

/** Start from exactly CARD_COUNT blank cards, filling in whatever the store has. */
function normalise(cards: ScreenCard[]): ScreenCard[] {
  return Array.from({ length: CARD_COUNT }, (_, i) => ({
    title: cards[i]?.title ?? "",
    entities: [...(cards[i]?.entities ?? [])],
  }));
}

/**
 * Screens — pick which Home Assistant entities appear on each of the robot's 3
 * display cards. dravix polls their state and pushes "Name  State" lines to the
 * ESPHome firmware's generic text slots. Self-contained: fetches screens + HA
 * entities, edits a local draft, saves via PUT /api/screens.
 */
export function ScreensPage() {
  const toasts = useToasts();

  const [cards, setCards] = useState<ScreenCard[]>(normalise([]));
  const [haEnts, setHaEnts] = useState<HaEntity[]>([]);
  const [haConfigured, setHaConfigured] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

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
      const [screens, ents] = await Promise.all([
        api.getScreens(),
        api.haEntities([]), // all domains — any entity can be shown on a card
      ]);
      if (!mounted.current) return;
      setCards(normalise(screens.screens));
      setHaEnts(ents.entities ?? []);
      setHaConfigured(ents.ha_configured);
    } catch (err) {
      if (mounted.current) toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [toasts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setTitle = (idx: number, title: string) =>
    setCards((cs) => cs.map((c, i) => (i === idx ? { ...c, title } : c)));

  const addEntity = (idx: number, entity_id: string) => {
    if (!entity_id) return;
    setCards((cs) =>
      cs.map((c, i) =>
        i === idx && !c.entities.includes(entity_id)
          ? { ...c, entities: [...c.entities, entity_id] }
          : c,
      ),
    );
  };

  const removeEntity = (idx: number, entity_id: string) =>
    setCards((cs) =>
      cs.map((c, i) =>
        i === idx
          ? { ...c, entities: c.entities.filter((e) => e !== entity_id) }
          : c,
      ),
    );

  async function save() {
    setSaving(true);
    try {
      // Only keep cards that actually have content — send a clean list.
      const clean = cards.filter((c) => c.title.trim() || c.entities.length);
      const res = await api.putScreens(clean);
      if (mounted.current) setCards(normalise(res.screens));
      toasts.ok("Screens saved — pushing to the robot");
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="space-y-5">
        {Array.from({ length: CARD_COUNT }).map((_, i) => (
          <div key={i} className="h-48 animate-pulse rounded-2xl bg-line/40" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <Panel eyebrow="display" title="Screens">
        <p className="font-mono text-[11px] leading-relaxed text-mute">
          Pick which Home Assistant entities show on each of the robot's three
          display cards. dravix polls their state every few seconds and pushes a
          title plus one <span className="text-soft">Name&nbsp;&nbsp;State</span>{" "}
          line per entity to the robot.
        </p>
        {!haConfigured && (
          <p className="mt-3 rounded-lg border border-amber/40 bg-amber/10 px-3 py-2 font-mono text-[11px] leading-relaxed text-amber">
            Home Assistant isn't connected — set the HA URL + token in the add-on
            config to pick entities.
          </p>
        )}
      </Panel>

      {cards.map((card, idx) => (
        <ScreenCardEditor
          key={idx}
          index={idx}
          card={card}
          haEnts={haEnts}
          haConfigured={haConfigured}
          onTitle={(t) => setTitle(idx, t)}
          onAdd={(e) => addEntity(idx, e)}
          onRemove={(e) => removeEntity(idx, e)}
        />
      ))}

      <div className="flex items-center justify-end rounded-2xl border border-line bg-panel/80 px-5 py-4 shadow-panel">
        <Button variant="primary" loading={saving} onClick={save}>
          ▸ Save screens
        </Button>
      </div>
    </div>
  );
}

function ScreenCardEditor({
  index,
  card,
  haEnts,
  haConfigured,
  onTitle,
  onAdd,
  onRemove,
}: {
  index: number;
  card: ScreenCard;
  haEnts: HaEntity[];
  haConfigured: boolean;
  onTitle: (title: string) => void;
  onAdd: (entity_id: string) => void;
  onRemove: (entity_id: string) => void;
}) {
  // Entities not yet on this card (so the picker never re-adds a duplicate).
  const available = haEnts.filter((e) => !card.entities.includes(e.entity_id));
  const nameOf = (id: string) =>
    haEnts.find((e) => e.entity_id === id)?.name ?? id;

  return (
    <Panel eyebrow={`card ${index + 1}`} title={card.title || `Card ${index + 1}`}>
      <div className="space-y-4">
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
            title
          </span>
          <input
            value={card.title}
            placeholder={`Card ${index + 1}`}
            onChange={(e) => onTitle(e.target.value)}
            className={inputCls}
          />
        </label>

        <div>
          <div className="eyebrow mb-2">entities</div>
          {card.entities.length === 0 ? (
            <p className="mb-2 font-mono text-[11px] text-mute">
              No entities yet — add some below.
            </p>
          ) : (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {card.entities.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => onRemove(id)}
                  title={`${id} · click to remove`}
                  className="group"
                >
                  <Chip tone="on">
                    <span className="truncate">{nameOf(id)}</span>
                    <span className="text-phosphor/60 group-hover:text-fault">
                      ✕
                    </span>
                  </Chip>
                </button>
              ))}
            </div>
          )}

          <select
            value=""
            disabled={!haConfigured}
            onChange={(e) => {
              onAdd(e.target.value);
              e.target.value = "";
            }}
            className={selectCls}
          >
            <option value="">
              {haConfigured ? "＋ add entity…" : "ha not connected"}
            </option>
            {available.map((e) => (
              <option key={e.entity_id} value={e.entity_id}>
                {e.name} · {e.entity_id}
              </option>
            ))}
          </select>
        </div>
      </div>
    </Panel>
  );
}
