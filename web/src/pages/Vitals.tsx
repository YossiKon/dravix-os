// Life — the robot's needs (energy/food/fun/calm), care buttons, and wellness tips.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import type { Vitals } from "../api";
import { Section, toast, toastErr } from "../ui";
import { useI18n } from "../i18n";

const NEEDS: { key: "energy" | "food" | "fun" | "calm"; he: string; en: string; icon: string; color: string }[] = [
  { key: "energy", he: "אנרגיה", en: "Energy", icon: "⚡", color: "#5dffa0" },
  { key: "food", he: "שובע", en: "Food", icon: "🍎", color: "#ffb84d" },
  { key: "fun", he: "כיף", en: "Fun", icon: "😄", color: "#33E6C8" },
  { key: "calm", he: "רוגע", en: "Calm", icon: "🧘", color: "#7bb0ff" },
];

const ACTIONS: { action: string; he: string; en: string; okHe: string; okEn: string }[] = [
  { action: "feed", he: "🍎 האכל", en: "🍎 Feed", okHe: "מ-מ-מ! טעים", okEn: "Yum!" },
  { action: "rest", he: "😴 נוח", en: "😴 Rest", okHe: "הולך לנמנם…", okEn: "Napping…" },
  { action: "play", he: "🎉 שחק", en: "🎉 Play", okHe: "כיף!", okEn: "Fun!" },
  { action: "calm", he: "🧘 הרגע", en: "🧘 Calm", okHe: "אההה, רגוע", okEn: "Ahh, calm" },
];

export function VitalsPage() {
  const { tr, lang } = useI18n();
  const [v, setV] = useState<Vitals | null>(null);
  const [busy, setBusy] = useState("");

  const refresh = useCallback(() => {
    apiGet<Vitals>("/api/vitals").then(setV).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 3000);
    return () => clearInterval(id);
  }, [refresh]);

  async function act(action: string, okMsg: string) {
    setBusy(action);
    try {
      const res = await apiSend<Vitals>("/api/vitals/action", "POST", { action });
      setV(res);
      toast(okMsg);
    } catch (e) {
      toastErr(e);
    } finally {
      setBusy("");
    }
  }

  async function toggleNudges() {
    if (!v) return;
    try {
      await apiSend("/api/vitals/nudges", "PUT", { enabled: !v.nudges });
      setV({ ...v, nudges: !v.nudges });
    } catch (e) {
      toastErr(e);
    }
  }

  return (
    <div className="space-y-4">
      <Section title={tr("החיים של הרובוט 💗", "The robot's life 💗")}>
        <div className="space-y-3">
          {NEEDS.map((n) => {
            const val = v ? Number(v[n.key]) : 0;
            return (
              <div key={n.key}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span>
                    {n.icon} {lang === "en" ? n.en : n.he}
                  </span>
                  <span className="font-mono text-mute">{val}%</span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-line">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${val}%`, background: n.color }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      <Section title={tr("טיפול", "Care")} delay={60}>
        <div className="grid grid-cols-2 gap-2">
          {ACTIONS.map((a) => (
            <button
              key={a.action}
              className="btn"
              disabled={busy === a.action}
              onClick={() => void act(a.action, lang === "en" ? a.okEn : a.okHe)}
            >
              {lang === "en" ? a.en : a.he}
            </button>
          ))}
        </div>
      </Section>

      <Section title={tr("טיפי רווחה", "Wellness tips")} delay={120}>
        <p className="mb-3 text-sm text-mute">
          {tr(
            "תזכורות בריאות למי שעובד ליד הרובוט — מנוחה לעיניים (20-20-20), לקום ולזוז, שתייה, יציבה. מופיעות על מסך הרובוט והוא מנענע כדי שתשים לב. שקט לגמרי במצב פוקוס/שינה.",
            "Health reminders for whoever works next to the robot — eye breaks (the 20-20-20 rule), stand up and move, hydrate, posture. They appear on the robot's screen and it wiggles so you notice. Completely silent in focus / sleep.",
          )}
        </p>
        <button className="btn w-full" onClick={() => void toggleNudges()}>
          {tr("טיפי רווחה", "Wellness tips")}: {v?.nudges ? tr("דלוקים ✓", "On ✓") : tr("כבויים", "Off")}
        </button>
      </Section>
    </div>
  );
}
