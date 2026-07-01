import { useCallback, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { clamp } from "../lib/format";
import { CAP, EXPRESSIONS, type Expression, type StatusResponse } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { exprMeta } from "./expressions";
import { Button, Panel, Toggle, cx } from "./ui";

const LED_PRESETS: { name: string; hex: string }[] = [
  { name: "white", hex: "#ffffff" },
  { name: "red", hex: "#ff5a52" },
  { name: "orange", hex: "#ffb454" },
  { name: "yellow", hex: "#ffe14d" },
  { name: "green", hex: "#5dffa0" },
  { name: "cyan", hex: "#5cc8ff" },
  { name: "blue", hex: "#5b8cff" },
  { name: "purple", hex: "#b07cff" },
  { name: "pink", hex: "#ff6ec7" },
];

const HEAD_SPEED = 0.5; // fixed, sensible default

export function ManualControl({
  status,
  onRefresh,
}: {
  status: StatusResponse | null;
  onRefresh?: () => void;
}) {
  const toasts = useToasts();
  const [idleBusy, setIdleBusy] = useState(false);

  const caps = new Set(status?.robot.capabilities ?? []);
  const canFace = caps.has(CAP.setFace);
  const canHead = caps.has(CAP.moveHead);
  const canLeds = caps.has(CAP.setLeds);
  const canSay = caps.has(CAP.say);
  const ready = status !== null;
  const idleMotion = status?.idle_motion ?? false;
  const nothing = ready && !canFace && !canHead && !canLeds && !canSay;

  function onError(err: unknown) {
    toasts.error(err instanceof ApiError ? err.detail : String(err));
  }

  async function toggleIdleMotion(next: boolean) {
    setIdleBusy(true);
    try {
      const res = await api.setIdleMotion(next);
      toasts.ok(`Idle motion ${res.idle_motion ? "on" : "off"}`);
      onRefresh?.();
    } catch (err) {
      onError(err);
    } finally {
      setIdleBusy(false);
    }
  }

  return (
    <Panel eyebrow="actuators" title="Manual Control">
      {!ready ? (
        <p className="font-mono text-[11px] text-mute">Awaiting robot telemetry…</p>
      ) : nothing ? (
        <p className="font-mono text-[11px] text-mute">
          No controls available for this robot.
        </p>
      ) : (
        <div className="space-y-6">
          {canFace && (
            <ExpressionPicker
              current={status?.robot.expression}
              onPick={async (e) => {
                try {
                  await api.face(e);
                  toasts.ok(`Face → ${e}`);
                } catch (err) {
                  onError(err);
                }
              }}
            />
          )}

          {canHead && (
            <HeadControl
              onMove={async (yaw, pitch) => {
                try {
                  await api.head(yaw, pitch, HEAD_SPEED);
                } catch (err) {
                  onError(err);
                }
              }}
              idleMotion={idleMotion}
              idleMotionDisabled={idleBusy}
              onToggleIdleMotion={toggleIdleMotion}
            />
          )}

          {canLeds && (
            <LedControl
              onApply={async (color, brightness) => {
                try {
                  await api.leds(color, brightness);
                  toasts.ok(`LEDs → ${color} @ ${Math.round(brightness * 100)}%`);
                } catch (err) {
                  onError(err);
                }
              }}
            />
          )}

          {canSay && (
            <SayControl
              onSay={async (text) => {
                try {
                  await api.say(text);
                  toasts.ok("Spoken");
                  return true;
                } catch (err) {
                  onError(err);
                  return false;
                }
              }}
            />
          )}
        </div>
      )}
    </Panel>
  );
}

/* ── Expression picker ──────────────────────────────────────────────────── */
function ExpressionPicker({
  current,
  onPick,
}: {
  current?: string;
  onPick: (e: Expression) => void;
}) {
  return (
    <ControlBlock label="Face">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {EXPRESSIONS.map((e) => {
          const meta = exprMeta(e);
          const selected = current === e;
          return (
            <button
              key={e}
              onClick={() => onPick(e)}
              className={cx(
                "group flex flex-col items-center gap-1.5 rounded-xl border py-3 transition-all",
                selected
                  ? cx(meta.ring, "shadow-glow")
                  : "border-line bg-panel-2/40 hover:border-line-bright hover:bg-panel-2",
              )}
            >
              <span
                className={cx(
                  "font-mono text-base leading-none",
                  selected ? meta.accent : "text-soft group-hover:text-ink",
                )}
              >
                {meta.emoji}
              </span>
              <span
                className={cx(
                  "font-mono text-[10px] uppercase tracking-wide",
                  selected ? meta.accent : "text-mute",
                )}
              >
                {e}
              </span>
            </button>
          );
        })}
      </div>
    </ControlBlock>
  );
}

/* ── Head control (2D joystick pad) ─────────────────────────────────────── */
function HeadControl({
  onMove,
  idleMotion,
  idleMotionDisabled,
  onToggleIdleMotion,
}: {
  onMove: (yaw: number, pitch: number) => void;
  idleMotion: boolean;
  idleMotionDisabled: boolean;
  onToggleIdleMotion: (next: boolean) => void;
}) {
  // Knob position as a fraction of half-extent, x ∈ [-1,1], y ∈ [-1,1]
  // where +y on screen is DOWN. Yaw/pitch derive from this.
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const padRef = useRef<HTMLDivElement>(null);

  // Normalised aim in [-1,1]. yaw = pad x; screen up (negative y) → look up (positive pitch).
  const round2 = (n: number) => Math.round(n * 100) / 100;
  const yaw = round2(pos.x);
  const pitch = round2(-pos.y);

  const send = useCallback(
    (ny: number, np: number) => {
      onMove(clamp(ny, -1, 1), clamp(np, -1, 1));
    },
    [onMove],
  );

  const pointFromEvent = useCallback((clientX: number, clientY: number) => {
    const el = padRef.current;
    if (!el) return null;
    const r = el.getBoundingClientRect();
    // Map to [-1,1] with 0 at centre; clamp to the circular-ish square.
    const x = clamp(((clientX - r.left) / r.width) * 2 - 1, -1, 1);
    const y = clamp(((clientY - r.top) / r.height) * 2 - 1, -1, 1);
    return { x, y };
  }, []);

  // Dragging only moves the knob locally — we send ONE command on release, so the serial
  // servo bus isn't flooded with ~10 requests/sec (which was overwhelming it).
  function handlePointerDown(e: React.PointerEvent<HTMLDivElement>) {
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const pt = pointFromEvent(e.clientX, e.clientY);
    if (pt) setPos(pt);
  }

  function handlePointerMove(e: React.PointerEvent<HTMLDivElement>) {
    if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
    const pt = pointFromEvent(e.clientX, e.clientY);
    if (pt) setPos(pt); // visual only — no request while dragging
  }

  function handlePointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
    (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    // Send exactly once, at the resting position.
    const pt = pointFromEvent(e.clientX, e.clientY);
    if (pt) {
      setPos(pt);
      send(round2(pt.x), round2(-pt.y));
    } else {
      send(yaw, pitch);
    }
  }

  function center() {
    setPos({ x: 0, y: 0 });
    send(0, 0);
  }

  return (
    <ControlBlock
      label="Head"
      right={
        <Button variant="subtle" onClick={center}>
          ⌖ Center
        </Button>
      }
    >
      <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-start sm:gap-5">
        {/* Joystick pad */}
        <div
          ref={padRef}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          className={cx(
            "relative h-[180px] w-[180px] shrink-0 cursor-grab touch-none select-none rounded-2xl",
            "border border-line bg-void/70 active:cursor-grabbing",
          )}
        >
          {/* grid */}
          <div className="pointer-events-none absolute inset-0 rounded-2xl [background:linear-gradient(rgba(255,255,255,0.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.04)_1px,transparent_1px)] [background-size:20px_20px]" />
          {/* crosshair */}
          <span className="pointer-events-none absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-line-bright/50" />
          <span className="pointer-events-none absolute left-0 top-1/2 h-px w-full -translate-y-1/2 bg-line-bright/50" />
          {/* centre ring */}
          <span className="pointer-events-none absolute left-1/2 top-1/2 h-10 w-10 -translate-x-1/2 -translate-y-1/2 rounded-full border border-line/60" />
          {/* knob */}
          <span
            className="pointer-events-none absolute h-6 w-6 -translate-x-1/2 -translate-y-1/2 rounded-full bg-phosphor shadow-glow ring-2 ring-phosphor/30"
            style={{
              left: `${(pos.x + 1) * 50}%`,
              top: `${(pos.y + 1) * 50}%`,
            }}
          />
        </div>

        {/* Readout + idle toggle */}
        <div className="w-full flex-1 space-y-3">
          <div className="rounded-xl border border-line bg-panel-2/40 px-3.5 py-3">
            <div className="font-mono text-[10px] uppercase tracking-wider text-mute">
              Direction
            </div>
            <div className="mt-1 font-mono text-sm tabular-nums text-ink">
              yaw <span className="text-phosphor">{Math.round(yaw * 100)}%</span>
              <span className="mx-1.5 text-mute">·</span>
              pitch <span className="text-phosphor">{Math.round(pitch * 100)}%</span>
            </div>
            <p className="mt-1 font-mono text-[10px] text-mute">
              drag the knob, release to aim the head
            </p>
          </div>

          {/* Idle motion: ambient automatic head glances */}
          <div className="flex items-center justify-between gap-3 rounded-xl border border-line bg-panel-2/40 px-3.5 py-2.5">
            <div className="min-w-0">
              <div className="font-mono text-[11px] uppercase tracking-wide text-soft">
                Idle motion
              </div>
              <p className="truncate font-mono text-[10px] text-mute">
                occasional head glances
              </p>
            </div>
            <Toggle
              on={idleMotion}
              disabled={idleMotionDisabled}
              label="Idle motion"
              onChange={onToggleIdleMotion}
            />
          </div>
        </div>
      </div>
    </ControlBlock>
  );
}

/* ── LED control ────────────────────────────────────────────────────────── */
function LedControl({
  onApply,
}: {
  onApply: (color: string, brightness: number) => void;
}) {
  const [color, setColor] = useState("#5dffa0");
  const [brightness, setBrightness] = useState(0.8);

  return (
    <ControlBlock
      label="LEDs"
      right={
        <Button variant="primary" onClick={() => onApply(color, brightness)}>
          Apply
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        {LED_PRESETS.map((c) => (
          <button
            key={c.name}
            title={c.name}
            onClick={() => setColor(c.hex)}
            className={cx(
              "h-8 w-8 rounded-full border-2 transition-transform",
              color.toLowerCase() === c.hex.toLowerCase()
                ? "scale-110 border-ink"
                : "border-line hover:scale-105 hover:border-line-bright",
            )}
            style={{
              backgroundColor: c.hex,
              boxShadow:
                color.toLowerCase() === c.hex.toLowerCase()
                  ? `0 0 14px -2px ${c.hex}`
                  : undefined,
            }}
          />
        ))}
        <label
          className="relative ml-1 grid h-8 w-8 cursor-pointer place-items-center rounded-full border-2 border-dashed border-line text-mute hover:border-line-bright"
          title="Custom color"
        >
          <span className="font-mono text-xs">+</span>
          <input
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className="absolute inset-0 cursor-pointer opacity-0"
          />
        </label>
        <span className="ml-auto font-mono text-[11px] uppercase tracking-wider text-soft">
          {color}
        </span>
      </div>
      <div className="mt-3">
        <Slider
          label="brightness"
          min={0}
          max={1}
          step={0.05}
          value={brightness}
          format={(v) => `${Math.round(v * 100)}%`}
          onChange={setBrightness}
        />
      </div>
    </ControlBlock>
  );
}

/* ── Say control (literal speech) ───────────────────────────────────────── */
function SayControl({
  onSay,
}: {
  onSay: (text: string) => Promise<boolean>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    const ok = await onSay(t);
    setBusy(false);
    if (ok) setText("");
  }

  return (
    <ControlBlock label="Say">
      <textarea
        value={text}
        placeholder="Type exactly what the robot should speak…"
        rows={2}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit();
        }}
        className={cx(
          "w-full resize-none rounded-xl border border-line bg-void/60 px-3.5 py-3",
          "font-body text-sm text-ink placeholder:text-mute/70",
          "focus:border-phosphor/50 focus:outline-none focus:ring-1 focus:ring-phosphor/30",
        )}
      />
      <div className="mt-2 flex items-center justify-between">
        <span className="font-mono text-[10px] text-mute">⌘/Ctrl + Enter</span>
        <Button
          variant="primary"
          loading={busy}
          disabled={!text.trim()}
          onClick={submit}
        >
          ▸ Speak
        </Button>
      </div>
    </ControlBlock>
  );
}

/* ── shared sub-components ──────────────────────────────────────────────── */
function ControlBlock({
  label,
  right,
  children,
}: {
  label: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <span className="eyebrow">{label}</span>
        {right}
      </div>
      {children}
    </div>
  );
}

function Slider({
  label,
  min,
  max,
  step,
  value,
  suffix,
  format,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  suffix?: string;
  format?: (v: number) => string;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-wider text-mute">
          {label}
        </span>
        <span className="font-mono text-xs tabular-nums text-ink">
          {format ? format(value) : `${value}${suffix ?? ""}`}
        </span>
      </div>
      <input
        type="range"
        className="slider"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
