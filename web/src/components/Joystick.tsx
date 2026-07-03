// Head joystick — drag anywhere on the pad; the command is sent ONCE, on release
// (the serial servo bus hates being flooded). Up = pitch +1, right = yaw +1.
import { useRef, useState } from "react";
import { useI18n } from "../i18n";

export function Joystick(props: { onRelease: (yaw: number, pitch: number) => void }) {
  const { tr } = useI18n();
  const pad = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null); // -1..1, screen coords

  function toNorm(e: { clientX: number; clientY: number }): { x: number; y: number } {
    const el = pad.current;
    if (!el) return { x: 0, y: 0 };
    const r = el.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 2 - 1;
    const y = ((e.clientY - r.top) / r.height) * 2 - 1;
    const clamp = (v: number) => Math.max(-1, Math.min(1, v));
    return { x: clamp(x), y: clamp(y) };
  }

  return (
    <div
      ref={pad}
      className="relative mx-auto aspect-square w-full max-w-64 touch-none select-none rounded-3xl border border-line-2 bg-bg"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        setPos(toNorm(e));
      }}
      onPointerMove={(e) => {
        if (pos !== null) setPos(toNorm(e));
      }}
      onPointerUp={(e) => {
        const p = toNorm(e);
        setPos(null);
        props.onRelease(p.x, -p.y); // screen-y down → pitch up is negative screen-y
      }}
      onPointerCancel={() => setPos(null)}
    >
      {/* crosshair */}
      <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px bg-line" />
      <div className="pointer-events-none absolute inset-y-0 left-1/2 w-px bg-line" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-line" />
      {/* labels */}
      <span className="pointer-events-none absolute left-1/2 top-2 -translate-x-1/2 text-xs text-mute">{tr("למעלה", "Up")}</span>
      <span className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2 text-xs text-mute">{tr("למטה", "Down")}</span>
      {/* thumb */}
      <div
        className={`pointer-events-none absolute h-14 w-14 rounded-full border-2 transition-colors ${
          pos ? "border-teal bg-teal/25 shadow-led-teal" : "border-line-2 bg-card2"
        }`}
        style={{
          left: `calc(${(((pos?.x ?? 0) + 1) / 2) * 100}% - 28px)`,
          top: `calc(${(((pos?.y ?? 0) + 1) / 2) * 100}% - 28px)`,
        }}
      />
    </div>
  );
}
