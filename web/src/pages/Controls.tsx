// Dravix — Controls & gestures reference. Every way to drive the robot: the touchscreen face,
// the wireless joystick, the permission prompt, and the physical touch / proximity sensors.
import { useEffect, useState } from "react";
import { apiGet, apiSend } from "../api";
import { Section } from "../ui";
import { useI18n } from "../i18n";

type Row = [heG: string, enG: string, heA: string, enA: string];

function Rows({ rows }: { rows: Row[] }) {
  const { tr } = useI18n();
  return (
    <div className="divide-y divide-line">
      {rows.map((r, i) => (
        <div key={i} className="flex items-start justify-between gap-4 py-2">
          <span className="shrink-0 font-semibold">{tr(r[0], r[1])}</span>
          <span className="text-end text-sm text-mute">{tr(r[2], r[3])}</span>
        </div>
      ))}
    </div>
  );
}

// Face cosmetics — one tap sends /api/robot/accessory; the robot shows it (default None = bare).
const ACCESSORIES: [string, string, string][] = [
  ["None", "🚫", "בלי"],
  ["Glasses", "👓", "משקפיים"],
  ["Sunglasses", "🕶️", "משקפי שמש"],
  ["Top hat", "🎩", "צילינדר"],
  ["Cap", "🧢", "כובע"],
  ["Crown", "👑", "כתר"],
  ["Bow tie", "🎀", "פפיון"],
  ["Headphones", "🎧", "אוזניות"],
  ["Halo", "😇", "הילה"],
  ["Monocle", "🧐", "מונוקל"],
  ["Flower", "🌸", "פרח"],
  ["Mongkhon", "🥋", "מונגקון"],
  ["Boxing gloves", "🥊", "כפפות אגרוף"],
  ["Fight band", "🇹🇭", "סרט לחימה"],
  ["Fight shorts", "🩳", "מכנסי מואי-תאי"],
  ["Cat ears", "🐱", "אוזני חתול"],
  ["Beard", "🧔", "זקן"],
  ["Eye patch", "🏴‍☠️", "טלאי עין"],
  ["Mustache", "🥸", "שפם"],
  ["Shirt", "👔", "חולצה"],
  ["Necklace", "📿", "שרשרת"],
  ["Gold chain", "⛓️", "שרשרת זהב"],
];

const BACKGROUNDS: [string, string, string][] = [
  ["None", "🚫", "בלי"],
  ["Space", "🌌", "חלל"],
  ["Sunset", "🌅", "שקיעה"],
  ["Ocean", "🌊", "אוקיינוס"],
  ["Matrix", "🟩", "מטריקס"],
  ["Party", "🎉", "מסיבה"],
  ["Arena", "🥊", "זירה"],
];

// One grid, reused for accessories + backgrounds — POSTs {option} to its endpoint.
function CosmeticPicker({ endpoint, items }: { endpoint: string; items: [string, string, string][] }) {
  const { tr } = useI18n();
  const [cur, setCur] = useState("None");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    apiGet<{ current: string | null }>(endpoint)
      .then((r) => (r.current ? setCur(r.current) : undefined))
      .catch(() => undefined);
  }, [endpoint]);
  const pick = (opt: string) => {
    if (busy) return;
    setBusy(true);
    setCur(opt);
    apiSend(endpoint, "POST", { option: opt })
      .catch(() => undefined)
      .finally(() => setBusy(false));
  };
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map(([opt, emoji, he]) => (
        <button
          key={opt}
          type="button"
          disabled={busy}
          onClick={() => pick(opt)}
          className={`flex flex-col items-center gap-1 rounded-xl border py-2 text-xs transition active:scale-95 disabled:opacity-60 ${
            cur === opt ? "border-teal bg-card2 text-teal" : "border-line bg-card2/40 text-mute"
          }`}
        >
          <span className="text-2xl leading-none">{emoji}</span>
          {tr(he, opt)}
        </button>
      ))}
    </div>
  );
}

export function ControlsPage() {
  const { tr } = useI18n();
  return (
    <div className="space-y-1">
      <p className="px-1 pb-1 text-sm text-mute">
        {tr(
          "כל דרכי השליטה ברובוט — מסך-מגע, ג'ויסטיק, ראש וקרבה.",
          "Every way to control the robot — touchscreen, joystick, head and proximity.",
        )}
      </p>

      <Section title={tr("🎭 אקססוריז לפרצוף", "🎭 Face accessories")} delay={10}>
        <CosmeticPicker endpoint="/api/robot/accessory" items={ACCESSORIES} />
      </Section>

      <Section title={tr("🖼️ רקע לפרצוף", "🖼️ Face background")} delay={15}>
        <CosmeticPicker endpoint="/api/robot/background" items={BACKGROUNDS} />
      </Section>

      <Section title={tr("🖥️ מסך-המגע (הפרצוף)", "🖥️ Touchscreen (the face)")} delay={20}>
        <Rows
          rows={[
            ["טאפ 1", "1 tap", "כלום", "nothing"],
            ["טאפ 2 (דאבל)", "2 taps (double)", "🎙️ הפעל/בטל AI", "🎙️ toggle the AI"],
            ["טאפ 3 (טריפל)", "3 taps (triple)", "🛑 עצור הכל", "🛑 stop everything"],
            ["לחיצה ארוכה ~1.2ש׳", "long-press ~1.2s", "😴 שינה", "😴 sleep"],
            ["נגיעה כשישן", "touch while asleep", "☀️ התעוררות", "☀️ wake up"],
            ["החלקה ↓", "swipe down", "סרגל-סטטוס", "status bar"],
            ["החלקה ↑", "swipe up", "חזרה לפרצוף", "back to the face"],
            ["החלקה ←", "swipe left", "מסך הבא", "next screen"],
            ["החלקה →", "swipe right", "מסך קודם", "previous screen"],
            ["גרירה אופקית בסרגל-סטטוס", "drag on the status bar", "🎚️ סליידר (ווליום/בהירות/לד)", "🎚️ slider (volume/brightness/LED)"],
          ]}
        />
      </Section>

      <Section title={tr("🕹️ הג'ויסטיק (השלט האלחוטי ESP-NOW)", "🕹️ The joystick (ESP-NOW remote)")} delay={40}>
        <Rows
          rows={[
            ["מוט — כיוון", "stick — direction", "מזיז את ראש הרובוט · שולט במשחקים (מגש / כיוון / כוונת / הליכה)", "moves the robot's head · steers the games (paddle / aim / walk)"],
            ["כפתור", "button", "דבר עם ה-AI · יורה (Doom) · קופץ (Maple)", "talk to the AI · shoot (Doom) · jump (Maple)"],
          ]}
        />
      </Section>

      <Section title={tr("✋ בקשת-אישור (Permission)", "✋ Permission request")} delay={60}>
        <Rows
          rows={[
            ["טאפ על הפרצוף", "tap the face", "✓ אישור", "✓ approve"],
            ["כפתור Approve הירוק", "green Approve button", "✓ אישור", "✓ approve"],
            ["כפתור Reject האדום", "red Reject button", "✗ דחייה", "✗ reject"],
            ["נגיעה בראש", "touch the head", "✓ אישור", "✓ approve"],
          ]}
        />
      </Section>

      <Section title={tr("🐾 נגיעה פיזית + קרבה", "🐾 Physical touch + proximity")} delay={80}>
        <Rows
          rows={[
            ["ליטוף הראש", "pet the head", "💗 מאושר, מתחכך בכף-היד", "💗 happy, nuzzles your hand"],
            ["דגדוג (חיישן שני)", "tickle (2nd sensor)", "😆 תגובת-דגדוג", "😆 giggles"],
            ["אצבע צמודה (boop)", "finger up close (boop)", "♥ אהבה + 🙈 מתבייש", "♥ love + 🙈 bashful"],
            ["התקרבות", "approach", "👋 ברכה + נפנוף", "👋 greets + waves"],
            ["נפנוף יד (3 תנועות)", "wave (3 swings)", "👋 מנפנף בחזרה", "👋 waves back"],
            ["סיבוב הראש ביד", "turn the head by hand", "😲 \"הֵי!?\" מופתע", "😲 startled \"hey!?\""],
          ]}
        />
      </Section>

      <p className="px-1 pt-2 text-xs text-mute">
        {tr(
          "מחוות הליטוף / דגדוג / boop / נפנוף / סיבוב-ראש תלויות בחיישנים הפיזיים של הרובוט (מגע + קרבה). מחוות מסך-המגע והג'ויסטיק עובדות תמיד.",
          "The pet / tickle / boop / wave / head-turn gestures depend on the robot's physical sensors (touch + proximity). The touchscreen and joystick gestures always work.",
        )}
      </p>
    </div>
  );
}
