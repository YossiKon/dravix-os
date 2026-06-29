import { useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";
import { clamp } from "../lib/format";
import { CAP, EXPRESSIONS, type Expression, type StatusResponse } from "../lib/types";
import { useToasts } from "../hooks/useToasts";
import { exprMeta } from "./expressions";
import { Button, Panel, cx } from "./ui";

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

export function ManualControl({ status }: { status: StatusResponse | null }) {
  const toasts = useToasts();
  const caps = new Set(status?.robot.capabilities ?? []);
  const canFace = caps.has(CAP.setFace);
  const canHead = caps.has(CAP.moveHead);
  const canLeds = caps.has(CAP.setLeds);
  const ready = status !== null;

  function onError(err: unknown) {
    toasts.error(err instanceof ApiError ? err.detail : String(err));
  }

  return (
    <Panel eyebrow="actuators" title="Manual Control">
      <div className="space-y-6">
        <ExpressionPicker
          disabled={!ready || !canFace}
          current={status?.robot.expression}
          reason={!canFace ? "Driver lacks set_face" : undefined}
          onPick={async (e) => {
            try {
              await api.face(e);
              toasts.ok(`Face → ${e}`);
            } catch (err) {
              onError(err);
            }
          }}
        />

        <HeadControl
          disabled={!ready || !canHead}
          reason={!canHead ? "Driver lacks move_head" : undefined}
          yaw={status?.robot.head_yaw ?? 0}
          pitch={status?.robot.head_pitch ?? 0}
          onMove={async (yaw, pitch, speed) => {
            try {
              await api.head(yaw, pitch, speed);
            } catch (err) {
              onError(err);
            }
          }}
        />

        <LedControl
          disabled={!ready || !canLeds}
          reason={!canLeds ? "Driver lacks set_leds" : undefined}
          onApply={async (color, brightness) => {
            try {
              await api.leds(color, brightness);
              toasts.ok(`LEDs → ${color} @ ${Math.round(brightness * 100)}%`);
            } catch (err) {
              onError(err);
            }
          }}
        />
      </div>
    </Panel>
  );
}

/* ── Expression picker ──────────────────────────────────────────────────── */
function ExpressionPicker({
  current,
  disabled,
  reason,
  onPick,
}: {
  current?: string;
  disabled: boolean;
  reason?: string;
  onPick: (e: Expression) => void;
}) {
  return (
    <ControlBlock label="Expression" disabled={disabled} reason={reason}>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {EXPRESSIONS.map((e) => {
          const meta = exprMeta(e);
          const selected = current === e;
          return (
            <button
              key={e}
              disabled={disabled}
              onClick={() => onPick(e)}
              className={cx(
                "group flex flex-col items-center gap-1.5 rounded-xl border py-3 transition-all",
                "disabled:cursor-not-allowed disabled:opacity-40",
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

/* ── Head control ───────────────────────────────────────────────────────── */
function HeadControl({
  yaw,
  pitch,
  disabled,
  reason,
  onMove,
}: {
  yaw: number;
  pitch: number;
  disabled: boolean;
  reason?: string;
  onMove: (yaw: number, pitch: number, speed: number) => void;
}) {
  const [y, setY] = useState(yaw);
  const [p, setP] = useState(pitch);
  const [speed, setSpeed] = useState(0.7);
  const dirty = useRef(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync from telemetry while the user isn't actively dragging.
  useEffect(() => {
    if (!dirty.current) {
      setY(yaw);
      setP(pitch);
    }
  }, [yaw, pitch]);

  function commit(ny: number, np: number) {
    dirty.current = true;
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      onMove(clamp(ny, -180, 180), clamp(np, -90, 90), speed);
      // Allow telemetry to resync shortly after a move settles.
      setTimeout(() => (dirty.current = false), 1200);
    }, 120);
  }

  function center() {
    setY(0);
    setP(0);
    dirty.current = true;
    onMove(0, 0, speed);
    setTimeout(() => (dirty.current = false), 1200);
  }

  return (
    <ControlBlock
      label="Head"
      disabled={disabled}
      reason={reason}
      right={
        <Button variant="subtle" disabled={disabled} onClick={center}>
          ⌖ Look center
        </Button>
      }
    >
      {/* Visual crosshair readout */}
      <div className="mb-4 flex items-center gap-4">
        <Crosshair yaw={y} pitch={p} />
        <div className="flex-1 space-y-3">
          <Slider
            label="yaw"
            min={-180}
            max={180}
            step={1}
            value={y}
            suffix="°"
            disabled={disabled}
            onChange={(v) => {
              setY(v);
              commit(v, p);
            }}
          />
          <Slider
            label="pitch"
            min={-90}
            max={90}
            step={1}
            value={p}
            suffix="°"
            disabled={disabled}
            onChange={(v) => {
              setP(v);
              commit(y, v);
            }}
          />
          <Slider
            label="speed"
            min={0}
            max={1}
            step={0.05}
            value={speed}
            format={(v) => v.toFixed(2)}
            disabled={disabled}
            onChange={setSpeed}
          />
        </div>
      </div>
    </ControlBlock>
  );
}

function Crosshair({ yaw, pitch }: { yaw: number; pitch: number }) {
  // Map yaw [-180,180] → x, pitch [-90,90] → y (inverted: up = look up).
  const x = ((clamp(yaw, -180, 180) + 180) / 360) * 100;
  const yv = ((clamp(-pitch, -90, 90) + 90) / 180) * 100;
  return (
    <div className="relative hidden h-24 w-24 shrink-0 rounded-lg border border-line bg-void/60 sm:block">
      <div className="absolute inset-0 [background:linear-gradient(rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.05)_1px,transparent_1px)] [background-size:12px_12px]" />
      <span className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-line-bright/60" />
      <span className="absolute top-1/2 left-0 h-px w-full -translate-y-1/2 bg-line-bright/60" />
      <span
        className="absolute h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-phosphor shadow-glow transition-all duration-200"
        style={{ left: `${x}%`, top: `${yv}%` }}
      />
    </div>
  );
}

/* ── LED control ────────────────────────────────────────────────────────── */
function LedControl({
  disabled,
  reason,
  onApply,
}: {
  disabled: boolean;
  reason?: string;
  onApply: (color: string, brightness: number) => void;
}) {
  const [color, setColor] = useState("#5dffa0");
  const [brightness, setBrightness] = useState(0.8);

  return (
    <ControlBlock
      label="LEDs"
      disabled={disabled}
      reason={reason}
      right={
        <Button
          variant="primary"
          disabled={disabled}
          onClick={() => onApply(color, brightness)}
        >
          Apply
        </Button>
      }
    >
      <div className="flex flex-wrap items-center gap-2">
        {LED_PRESETS.map((c) => (
          <button
            key={c.name}
            disabled={disabled}
            title={c.name}
            onClick={() => setColor(c.hex)}
            className={cx(
              "h-8 w-8 rounded-full border-2 transition-transform disabled:cursor-not-allowed disabled:opacity-40",
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
          className={cx(
            "relative ml-1 grid h-8 w-8 cursor-pointer place-items-center rounded-full border-2 border-dashed border-line text-mute hover:border-line-bright",
            disabled && "pointer-events-none opacity-40",
          )}
          title="Custom color"
        >
          <span className="font-mono text-xs">+</span>
          <input
            type="color"
            value={color}
            disabled={disabled}
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
          disabled={disabled}
          onChange={setBrightness}
        />
      </div>
    </ControlBlock>
  );
}

/* ── shared sub-components ──────────────────────────────────────────────── */
function ControlBlock({
  label,
  reason,
  disabled,
  right,
  children,
}: {
  label: string;
  reason?: string;
  disabled?: boolean;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="eyebrow">{label}</span>
          {disabled && reason && (
            <span className="rounded border border-amber/30 bg-amber/5 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-amber">
              {reason}
            </span>
          )}
        </div>
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
  disabled,
  onChange,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  suffix?: string;
  format?: (v: number) => string;
  disabled?: boolean;
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
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}
