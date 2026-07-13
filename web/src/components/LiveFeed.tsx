// Live activity feed — the robot's inner life as a small scrolling diary.
// Connects to /ws/events (works under HA ingress too — relative ws URL), seeds itself
// from /api/events/recent so it never starts empty, and reconnects with backoff.
import { useEffect, useRef, useState } from "react";
import { apiGet, wsUrl } from "../api";
import { Section } from "../ui";
import { useI18n } from "../i18n";

interface FeedEvent {
  type: string;
  data: Record<string, unknown>;
  ts: number;
}

// Only the events that tell a story — robot.head/robot.leds etc. are spam.
const LABELS: Record<string, { icon: string; he: string; en: string }> = {
  "touch.pet": { icon: "💗", he: "לוטף בראש", en: "petted on the head" },
  "touch.tap": { icon: "👆", he: "קיבל טאפ", en: "tapped" },
  "robot.touched": { icon: "🤗", he: "נגעו בו", en: "touched" },
  "user.spoke": { icon: "🗣", he: "שמע אותך", en: "heard you" },
  "robot.say": { icon: "💬", he: "אמר", en: "said" },
  "robot.face": { icon: "🎭", he: "החליף פרצוף", en: "changed face" },
  "robot.connected": { icon: "🟢", he: "התחבר", en: "connected" },
  "robot.disconnected": { icon: "🔴", he: "התנתק", en: "disconnected" },
  "mood.changed": { icon: "🌡", he: "מצב הרוח השתנה", en: "mood shifted" },
  "mood.idle": { icon: "🐾", he: "עשה משהו חמוד לבד", en: "did something cute on its own" },
  "vitals.nudge": { icon: "💧", he: "הזכיר טיפ רווחה", en: "shared a wellness tip" },
  "reaction.fired": { icon: "⚡", he: "ריאקציה הופעלה", en: "reaction fired" },
  "schedule.fired": { icon: "⏰", he: "משימה מתוזמנת רצה", en: "scheduled job ran" },
  "timer.done": { icon: "⏲", he: "טיימר הסתיים", en: "timer finished" },
  "birthday.celebrated": { icon: "🎂", he: "חגג יום הולדת!", en: "celebrated a birthday!" },
  "agent.status": { icon: "🤖", he: "עדכון מסוכן AI", en: "AI agent update" },
  "mode.activated": { icon: "▶", he: "מצב הופעל", en: "mode activated" },
  "mode.deactivated": { icon: "⏹", he: "מצב כובה", en: "mode stopped" },
  "presence.detected": { icon: "👋", he: "זיהה מישהו קרוב", en: "noticed someone near" },
  "presence.home": { icon: "🏠", he: "מישהו הגיע הביתה", en: "someone came home" },
  "face.seen": { icon: "🙂", he: "זיהה פרצוף מוכר", en: "recognized a face" },
  "guard.alert": { icon: "🚨", he: "התראת שמירה", en: "guard alert" },
};

function detail(e: FeedEvent): string {
  const d = e.data || {};
  if (e.type === "robot.say") return String(d.text ?? "").slice(0, 80);
  if (e.type === "mood.changed") return String(d.mood ?? "");
  if (e.type === "robot.face") return String(d.expression ?? "");
  if (e.type === "reaction.fired") return String(d.rule ?? "");
  if (e.type === "schedule.fired") return String(d.job ?? "");
  if (e.type === "timer.done") return String(d.label ?? "");
  if (e.type === "face.seen" || e.type === "presence.home") return String(d.person ?? d.name ?? "");
  if (e.type === "agent.status") {
    const w = d.winner as { name?: string; state?: string } | null;
    return w ? `${w.name}: ${String(w.state ?? "").replace("_", " ")}` : "";
  }
  if (e.type === "mode.activated" || e.type === "mode.deactivated") return String(d.name ?? "");
  return "";
}

export function LiveFeed() {
  const { tr, lang } = useI18n();
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const backoff = useRef(1000);

  const push = (e: FeedEvent) => {
    if (!LABELS[e.type]) return; // whitelist — head/led churn isn't a story
    setEvents((cur) => [...cur.slice(-49), e]);
  };

  useEffect(() => {
    let closed = false;
    // paint instantly from the server's short memory, then go live
    apiGet<{ events: FeedEvent[] }>("/api/events/recent")
      .then((r) => setEvents((r.events ?? []).filter((e) => LABELS[e.type]).slice(-50)))
      .catch(() => undefined);

    function connect() {
      if (closed) return;
      try {
        const ws = new WebSocket(wsUrl("ws/events"));
        wsRef.current = ws;
        ws.onmessage = (m) => {
          try {
            const e = JSON.parse(String(m.data)) as FeedEvent;
            if (e.type !== "ping") push(e);
          } catch {
            /* ignore bad frames */
          }
        };
        ws.onopen = () => {
          backoff.current = 1000;
        };
        ws.onclose = () => {
          if (!closed) {
            setTimeout(connect, backoff.current);
            backoff.current = Math.min(30000, backoff.current * 2);
          }
        };
      } catch {
        if (!closed) setTimeout(connect, backoff.current);
      }
    }
    connect();
    return () => {
      closed = true;
      wsRef.current?.close();
    };
  }, []);

  const ago = (ts: number) => {
    const s = Math.max(0, Math.round(Date.now() / 1000 - ts));
    if (s < 60) return tr("עכשיו", "now");
    if (s < 3600) return tr(`לפני ${Math.floor(s / 60)} דק׳`, `${Math.floor(s / 60)}m ago`);
    return tr(`לפני ${Math.floor(s / 3600)} ש׳`, `${Math.floor(s / 3600)}h ago`);
  };

  return (
    <Section title={tr("📜 היומן החי", "📜 Live diary")} delay={20}>
      <p className="mb-2 text-xs text-mute">
        {tr("מה עובר על הרובוט, ברגע שזה קורה.", "What the robot is up to, as it happens.")}
      </p>
      {events.length === 0 ? (
        <p className="text-sm text-mute">{tr("שקט בינתיים… לטף אותו 🐾", "Quiet so far… go pet it 🐾")}</p>
      ) : (
        <div className="max-h-72 space-y-1 overflow-y-auto pe-1">
          {[...events].reverse().map((e, i) => {
            const l = LABELS[e.type];
            const d = detail(e);
            return (
              <div key={`${e.ts}-${i}`} className="flex items-center gap-2 rounded-xl bg-card2/60 px-3 py-1.5 text-sm">
                <span aria-hidden>{l.icon}</span>
                <span className="min-w-0 flex-1 truncate">
                  {lang === "he" ? l.he : l.en}
                  {d && <span className="text-mute"> · {d}</span>}
                </span>
                <span className="shrink-0 text-xs text-mute">{ago(e.ts)}</span>
              </div>
            );
          })}
        </div>
      )}
    </Section>
  );
}
