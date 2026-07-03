// The hero: a live mirror of the robot — same face glyphs, same LED behaviour.
import { useEffect, useState } from "react";
import { biPick } from "../i18n";
import type { Lang } from "../i18n";

const STATE: Record<string, { he: string; en: string }> = {
  awake: { he: "ער", en: "Awake" },
  listening: { he: "מקשיב…", en: "Listening…" },
  speaking: { he: "מדבר…", en: "Speaking…" },
  screensaver: { he: "שומר מסך", en: "Screensaver" },
  sleep: { he: "ישן", en: "Asleep" },
  busy: { he: "עסוק", en: "Busy" },
  morning: { he: "בוקר טוב", en: "Good morning" },
  night: { he: "מצב לילה", en: "Night" },
  focus: { he: "מרוכז", en: "Focus" },
  quiet: { he: "מצב שקט", en: "Quiet" },
};

export function stateLabel(state: string | null, lang: Lang): string {
  if (!state) return biPick(lang, "לא ידוע", "Unknown");
  const s = STATE[state];
  return s ? biPick(lang, s.he, s.en) : state;
}

export function RobotFace(props: { state: string | null; online: boolean }) {
  const { state, online } = props;
  const [tick, setTick] = useState(0);
  const [blink, setBlink] = useState(false);

  // Animate: speaking mouth + sleeping zzz run on a slow tick, awake blinks now and then.
  useEffect(() => {
    const t = setInterval(() => setTick((v) => v + 1), 600);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (state !== "awake" && state !== null) return;
    let unblink: ReturnType<typeof setTimeout> | undefined;
    const t = setInterval(() => {
      setBlink(true);
      unblink = setTimeout(() => setBlink(false), 160);
    }, 3800);
    return () => {
      clearInterval(t);
      if (unblink !== undefined) clearTimeout(unblink);
    };
  }, [state]);

  let glyph = "o_o";
  if (!online) glyph = "x_x";
  else if (state === "sleep") glyph = ["u_u", "u_u z", "u_u zz", "u_u zzz"][tick % 4] as string;
  else if (state === "listening") glyph = "•_•";
  else if (state === "speaking") glyph = tick % 2 ? "o o" : "o_o";
  else if (blink) glyph = "-_-";
  else if (state === "busy" || state === "focus") glyph = ">_<";
  else if (state === "morning") glyph = "^_^";

  const talking = state === "listening" || state === "speaking";
  const asleep = state === "sleep" || state === "screensaver" || state === "night";

  return (
    <div className="overflow-hidden rounded-3xl border border-line bg-black shadow-card">
      {/* the "LCD" */}
      <div className="flex h-40 items-center justify-center">
        <span
          dir="ltr"
          className={`font-mono text-6xl font-bold transition-colors ${
            !online ? "text-red/70" : asleep ? "text-teal/45" : "text-teal"
          }`}
        >
          {glyph}
        </span>
      </div>
      {/* the LED bar — glows amber during an AI turn, exactly like the robot */}
      <div
        className={`mx-auto mb-3 h-2 w-2/3 rounded-full transition-all duration-500 ${
          talking ? "bg-amber shadow-led" : online && !asleep ? "bg-teal/25" : "bg-line"
        }`}
      />
    </div>
  );
}
