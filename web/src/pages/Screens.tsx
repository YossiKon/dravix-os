// מסכים — אילו ישויות HA יופיעו על 3 הכרטיסים של הרובוט (החלקה ימינה/שמאלה).
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { HAEntity, ScreenCard } from "../api";
import { EntityPicker } from "../components/EntityPicker";
import { Section, toast, toastErr } from "../ui";

const MAX_PER_CARD = 4;

export function ScreensPage(props: { entities: HAEntity[] }) {
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
      toast("נשמר — הכרטיסים יתעדכנו על הרובוט תוך רגע");
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
        מחליקים <b className="text-soft">ימינה / שמאלה</b> על מסך הרובוט כדי לעבור בין 3 כרטיסים. כאן בוחרים מה יופיע
        על כל אחד (עד {MAX_PER_CARD} ישויות לכרטיס).
      </p>
      {cards.map((card, i) => (
        <Section key={i} title={`כרטיס ${i + 1}`} delay={i * 70}>
          <label className="lbl">כותרת הכרטיס</label>
          <input
            className="inp mb-3"
            placeholder={`למשל: סלון / מזג אוויר / חיישנים`}
            value={card.title}
            onChange={(e) => patch(i, { title: e.target.value })}
          />
          <label className="lbl">ישויות להצגה</label>
          <div className="mb-2 flex flex-wrap gap-2">
            {card.entities.map((id) => (
              <span key={id} className="chip">
                {nameOf(id)}
                <button
                  type="button"
                  className="text-red"
                  aria-label="הסר"
                  onClick={() => patch(i, { entities: card.entities.filter((x) => x !== id) })}
                >
                  ✕
                </button>
              </span>
            ))}
            {card.entities.length === 0 && <span className="text-sm text-mute">עוד לא נבחרו ישויות</span>}
          </div>
          {card.entities.length < MAX_PER_CARD && (
            <EntityPicker
              entities={props.entities}
              value=""
              placeholder="＋ הוסף ישות…"
              onChange={(id) => {
                if (id && !card.entities.includes(id)) patch(i, { entities: [...card.entities, id] });
              }}
            />
          )}
        </Section>
      ))}
      <button className="btn btn-primary w-full" disabled={!loaded || saving} onClick={() => void save()}>
        {saving ? "שומר…" : "💾 שמור את הכרטיסים"}
      </button>
    </div>
  );
}
