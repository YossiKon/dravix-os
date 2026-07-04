// Screens — which HA entities appear on the robot's 3 cards (swipe left/right).
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { HAEntity, ScreenCard } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { Section, toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

const MAX_PER_CARD = 4;

export function ScreensPage(props: { entities: HAEntity[] }) {
  const { tr } = useI18n();
  const [cards, setCards] = useState<ScreenCard[]>([
    { title: "", entities: [] },
    { title: "", entities: [] },
    { title: "", entities: [] },
  ]);
  const [loaded, setLoaded] = useState(false);
  const [saving, setSaving] = useState(false);

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

  function patch(i: number, next: Partial<ScreenCard>) {
    setCards((cur) => cur.map((c, j) => (j === i ? { ...c, ...next } : c)));
  }

  async function save() {
    setSaving(true);
    try {
      await apiSend("/api/screens", "PUT", { screens: cards });
      toast(tr("נשמר — הכרטיסים יתעדכנו על הרובוט תוך רגע", "Saved — the cards update on the robot shortly"));
    } catch (e) {
      toastErr(e);
    } finally {
      setSaving(false);
    }
  }

  const nameOf = (id: string) => props.entities.find((e) => e.entity_id === id)?.name ?? id;

  return (
    <div className="space-y-4">
      <p className="animate-rise text-sm text-mute">
        {tr(
          `מחליקים ימינה / שמאלה על מסך הרובוט כדי לעבור בין 3 כרטיסים. כאן בוחרים מה יופיע על כל אחד (עד ${MAX_PER_CARD} ישויות לכרטיס) — וכל שורה על מסך הרובוט היא כפתור: נגיעה מדליקה/מכבה אור ומתג, לוחצת כפתור, מריצה סקריפט או מחליפה מצב מזגן. חיישנים מוצגים בלבד.`,
          `Swipe left / right on the robot's screen to move between the 3 cards. Here you pick what appears on each (up to ${MAX_PER_CARD} entities per card) — and every row on the robot's screen is a button: a tap toggles lights & switches, presses buttons, runs scripts, or flips the AC. Sensors are display-only.`,
        )}
      </p>
      {cards.map((card, i) => (
        <Section key={i} title={tr(`כרטיס ${i + 1}`, `Card ${i + 1}`)} delay={i * 70}>
          <label className="lbl">{tr("כותרת הכרטיס", "Card title")}</label>
          <input
            className="inp mb-3"
            placeholder={tr("למשל: סלון / מזג אוויר / חיישנים", "e.g. Living room / Weather / Sensors")}
            value={card.title}
            onChange={(e) => patch(i, { title: e.target.value })}
          />
          <label className="lbl">{tr("ישויות להצגה", "Entities to show")}</label>
          <div className="mb-2 flex flex-wrap gap-2">
            {card.entities.map((id) => (
              <span key={id} className="chip">
                {nameOf(id)}
                <button
                  type="button"
                  className="text-red"
                  aria-label={tr("הסר", "Remove")}
                  onClick={() => patch(i, { entities: card.entities.filter((x) => x !== id) })}
                >
                  ✕
                </button>
              </span>
            ))}
            {card.entities.length === 0 && (
              <span className="text-sm text-mute">{tr("עוד לא נבחרו ישויות", "No entities selected yet")}</span>
            )}
          </div>
          {card.entities.length < MAX_PER_CARD && (
            <EntityPicker
              entities={props.entities}
              value=""
              placeholder={tr("＋ הוסף ישות…", "＋ Add entity…")}
              onChange={(id) => {
                if (id && !card.entities.includes(id)) patch(i, { entities: [...card.entities, id] });
              }}
            />
          )}
        </Section>
      ))}
      <button className="btn btn-primary w-full" disabled={!loaded || saving} onClick={() => void save()}>
        {saving ? tr("שומר…", "Saving…") : tr("💾 שמור את הכרטיסים", "💾 Save cards")}
      </button>
    </div>
  );
}
