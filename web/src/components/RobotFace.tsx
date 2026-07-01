// The hero: a live mirror of the robot — same face glyphs, same LED behaviour.
import { useEffect, useState } from "react";

const STATE_HE: Record<string, string> = {
  awake: "ער",
  listening: "מקשיב…",
  speaking: "מדבר…",
  screensaver: "שומר מסך",
  sleep: "ישן",
  busy: "עסוק",
};

export function stateLabel(state: string | null): string {
  if (!state) return "לא ידוע";
  return STATE_HE[state] ?? state;
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
    const t = setInterval(() => {
      setBlink(true);
      setTimeout(() => setBlink(false), 160);
    }, 3800);
    return () => clearInterval(t);
  }, [state]);

  let glyph = "o_o";
  if (!online) glyph = "x_x";
  else if (state === "sleep") glyph = ["u_u", "u_u z", "u_u zz", "u_u zzz"][tick % 4] as string;
  else if (state === "listening") glyph = "•_•";
  else if (state === "speaking") glyph = tick % 2 ? "o o" : "o_o";
  else if (blink) glyph = "-_-";
  else if (state === "busy") glyph = ">_<";

  const talking = state === "listening" || state === "speaking";
  const asleep = state === "sleep" || state === "screensaver";

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
