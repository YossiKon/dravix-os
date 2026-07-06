// Dravix — Controls & gestures reference. Every way to drive the robot: the touchscreen face,
// the wireless joystick, the permission prompt, and the physical touch / proximity sensors.
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
