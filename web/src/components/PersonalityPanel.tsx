import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { humanize } from "../lib/format";
import type { InteractKind, Mood } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { exprMeta } from "./expressions";
import { Button, Meter, Panel, cx, errMsg } from "./ui";

const MOOD_POLL_MS = 5000;

const INTERACTS: { kind: InteractKind; label: string; glyph: string }[] = [
  { kind: "pet", label: "Pet", glyph: "🤚" },
  { kind: "tap", label: "Tap", glyph: "👆" },
  { kind: "spoke", label: "Talk", glyph: "💬" },
  { kind: "touched", label: "Touched", glyph: "✨" },
];

// A friendly glyph per known emote name; falls back to a star.
const EMOTE_GLYPH: Record<string, string> = {
  happy: "😄",
  love: "😍",
  fistbump: "🤜",
  curious: "🤔",
  yes: "👍",
  no: "👎",
  surprised: "😮",
  sleepy: "😴",
  wake: "🌅",
  sad: "😢",
};

// A friendly glyph + label per known fun game; falls back to a die.
const FUN_GLYPH: Record<string, string> = {
  dice: "🎲",
  coin: "🪙",
  "8ball": "🎱",
  joke: "😂",
  fortune: "🔮",
};

export function PersonalityPanel({
  initialMood,
  /** Bumps whenever a `mood.changed` WS event arrives → triggers a refetch. */
  moodTick = 0,
}: {
  initialMood?: Mood;
  moodTick?: number;
}) {
  const toasts = useToasts();
  const [mood, setMood] = useState<Mood | null>(initialMood ?? null);
  const [emotes, setEmotes] = useState<string[]>([]);
  const [games, setGames] = useState<string[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const refreshMood = useCallback(async () => {
    try {
      const m = await api.mood();
      if (mounted.current) setMood(m);
    } catch {
      /* keep last-known mood; surfaced elsewhere via status errors */
    }
  }, []);

  // Initial load of emotes + games + mood.
  useEffect(() => {
    api
      .emotes()
      .then((e) => mounted.current && setEmotes(e.emotes ?? []))
      .catch(() => {});
    api
      .fun()
      .then((f) => mounted.current && setGames(f.games ?? []))
      .catch(() => {});
    refreshMood();
  }, [refreshMood]);

  // Poll mood live + refetch on WS mood.changed.
  useEffect(() => {
    const id = setInterval(refreshMood, MOOD_POLL_MS);
    return () => clearInterval(id);
  }, [refreshMood]);
  useEffect(() => {
    if (moodTick > 0) refreshMood();
  }, [moodTick, refreshMood]);

  async function run(key: string, fn: () => Promise<unknown>, ok: string) {
    setBusy(key);
    try {
      await fn();
      toasts.ok(ok);
      // Mood likely shifted — pull the fresh values.
      refreshMood();
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  // Fun & voice: surface the robot's spoken `text` directly in the toast.
  async function speak(key: string, fn: () => Promise<{ text?: string }>) {
    setBusy(key);
    try {
      const res = await fn();
      toasts.ok(res?.text || "Done");
      refreshMood();
    } catch (err) {
      toasts.error(errMsg(err));
    } finally {
      if (mounted.current) setBusy(null);
    }
  }

  const exprFace = mood ? exprMeta(mood.expression) : undefined;

  return (
    <Panel
      eyebrow="personality"
      title="Mood & Affect"
      right={
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-mute">
          <span className="h-1.5 w-1.5 rounded-full bg-magenta shadow-[0_0_10px_2px_rgba(255,110,199,0.4)]" />
          live
        </div>
      }
    >
      <div className="space-y-6">
        {/* Current mood face + label */}
        <div className="flex items-center gap-4">
          <div
            className={cx(
              "grid h-20 w-20 shrink-0 place-items-center rounded-2xl border text-center",
              exprFace ? exprFace.ring : "border-line bg-panel-2/40",
            )}
          >
            <span
              className={cx(
                "font-mono text-xl leading-none",
                exprFace ? exprFace.accent : "text-soft",
              )}
            >
              {exprFace?.emoji ?? "·_·"}
            </span>
          </div>
          <div className="min-w-0">
            <div className="eyebrow mb-0.5">current mood</div>
            <div className="font-display text-2xl font-700 capitalize text-ink">
              {mood ? humanize(mood.mood) : "—"}
            </div>
            <div className="mt-1 font-mono text-[11px] uppercase tracking-wider text-soft">
              expression: {mood?.expression ?? "—"}
            </div>
          </div>
        </div>

        {/* Affect meters */}
        <div className="space-y-3">
          <Meter
            label="valence"
            value={mood?.valence ?? 0}
            display={mood ? mood.valence.toFixed(2) : "—"}
            color={(mood?.valence ?? 0) >= 0 ? "phosphor" : "amber"}
            signed
          />
          <Meter
            label="arousal"
            value={mood?.arousal ?? 0}
            display={mood ? mood.arousal.toFixed(2) : "—"}
            color="cyan"
          />
          <Meter
            label="affection"
            value={mood?.affection ?? 0}
            display={mood ? mood.affection.toFixed(2) : "—"}
            color="magenta"
          />
        </div>

        {/* Interact buttons */}
        <div>
          <div className="eyebrow mb-2 flex items-center gap-2">
            interact
            <span className="h-px flex-1 bg-line/70" />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {INTERACTS.map((i) => (
              <Button
                key={i.kind}
                variant="subtle"
                loading={busy === `int:${i.kind}`}
                disabled={busy !== null && busy !== `int:${i.kind}`}
                onClick={() =>
                  run(
                    `int:${i.kind}`,
                    () => api.interact(i.kind),
                    `${i.label} — mood nudged`,
                  )
                }
                className="flex-col gap-1 py-3"
              >
                <span aria-hidden className="text-base leading-none">
                  {i.glyph}
                </span>
                {i.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Emotes grid */}
        <div>
          <div className="eyebrow mb-2 flex items-center gap-2">
            emotes
            <span className="h-px flex-1 bg-line/70" />
          </div>
          {emotes.length === 0 ? (
            <p className="font-mono text-[11px] text-mute">No emotes available.</p>
          ) : (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {emotes.map((name) => (
                <button
                  key={name}
                  disabled={busy !== null && busy !== `emote:${name}`}
                  onClick={() =>
                    run(
                      `emote:${name}`,
                      () => api.emote(name),
                      `Emote → ${name}`,
                    )
                  }
                  className={cx(
                    "group flex flex-col items-center gap-1 rounded-xl border border-line bg-panel-2/40 py-2.5 transition-all",
                    "hover:border-magenta/50 hover:bg-magenta/[0.06]",
                    "disabled:cursor-not-allowed disabled:opacity-40",
                  )}
                  title={`Play emote: ${name}`}
                >
                  <span aria-hidden className="text-lg leading-none">
                    {EMOTE_GLYPH[name] ?? "✦"}
                  </span>
                  <span className="font-mono text-[9px] uppercase tracking-wide text-mute group-hover:text-soft">
                    {name}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Fun & voice */}
        <div>
          <div className="eyebrow mb-2 flex items-center gap-2">
            fun &amp; voice
            <span className="h-px flex-1 bg-line/70" />
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {(games ?? []).map((name) => (
              <Button
                key={name}
                variant="subtle"
                loading={busy === `fun:${name}`}
                disabled={busy !== null && busy !== `fun:${name}`}
                onClick={() =>
                  speak(`fun:${name}`, () => api.playFun(name))
                }
                className="flex-col gap-1 py-3"
                title={`Play ${name}`}
              >
                <span aria-hidden className="text-base leading-none">
                  {FUN_GLYPH[name] ?? "🎲"}
                </span>
                {humanize(name)}
              </Button>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <Button
              variant="primary"
              loading={busy === "say:time"}
              disabled={busy !== null && busy !== "say:time"}
              onClick={() => speak("say:time", () => api.sayTime())}
              className="flex-col gap-1 py-3"
            >
              <span aria-hidden className="text-base leading-none">
                🕒
              </span>
              Say time
            </Button>
            <Button
              variant="primary"
              loading={busy === "say:weather"}
              disabled={busy !== null && busy !== "say:weather"}
              onClick={() => speak("say:weather", () => api.sayWeather())}
              className="flex-col gap-1 py-3"
            >
              <span aria-hidden className="text-base leading-none">
                🌤️
              </span>
              Say weather
            </Button>
          </div>
        </div>
      </div>
    </Panel>
  );
}
