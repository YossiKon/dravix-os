import { useToasts, type ToastKind } from "../hooks/useToasts";
import { cx } from "./ui";

const styles: Record<ToastKind, { bar: string; icon: string; glyph: string }> = {
  ok: { bar: "bg-phosphor", icon: "text-phosphor", glyph: "✓" },
  error: { bar: "bg-fault", icon: "text-fault", glyph: "!" },
  info: { bar: "bg-cyan", icon: "text-cyan", glyph: "i" },
};

export function Toaster() {
  const { toasts, dismiss } = useToasts();

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-4 sm:items-end sm:p-6">
      {toasts.map((t) => {
        const s = styles[t.kind];
        return (
          <button
            key={t.id}
            onClick={() => dismiss(t.id)}
            className={cx(
              "pointer-events-auto flex w-full max-w-sm items-start gap-3 overflow-hidden rounded-xl",
              "border border-line bg-panel-2/95 py-3 pl-3 pr-4 text-left shadow-panel backdrop-blur",
              "animate-slide-in",
            )}
          >
            <span className={cx("h-full w-1 self-stretch rounded-full", s.bar)} />
            <span
              className={cx(
                "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full border border-current font-mono text-[11px]",
                s.icon,
              )}
            >
              {s.glyph}
            </span>
            <span className="pt-0.5 font-mono text-[12.5px] leading-snug text-ink">
              {t.message}
            </span>
          </button>
        );
      })}
    </div>
  );
}
