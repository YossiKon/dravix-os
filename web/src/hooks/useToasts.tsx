import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastKind = "ok" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastApi {
  toasts: Toast[];
  push: (kind: ToastKind, message: string) => void;
  ok: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
  dismiss: (id: number) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const idRef = useRef(1);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    const handle = timers.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback(
    (kind: ToastKind, message: string) => {
      const id = idRef.current++;
      setToasts((t) => [...t.slice(-4), { id, kind, message }]);
      const handle = setTimeout(() => dismiss(id), kind === "error" ? 6000 : 3500);
      timers.current.set(id, handle);
    },
    [dismiss],
  );

  const value = useMemo<ToastApi>(
    () => ({
      toasts,
      push,
      dismiss,
      ok: (m) => push("ok", m),
      error: (m) => push("error", m),
      info: (m) => push("info", m),
    }),
    [toasts, push, dismiss],
  );

  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToasts(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToasts must be used within <ToastProvider>");
  return ctx;
}
