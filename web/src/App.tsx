// דרביקס — שלט רחוק לרובוט. 4 טאבים: בית · מסכים · מזגן · הגדרות.
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "./api";
import type { HAEntity, Health, RobotConfig } from "./api";
import { HomePage } from "./pages/Home";
import { ScreensPage } from "./pages/Screens";
import { ClimatePage } from "./pages/Climate";
import { SettingsPage } from "./pages/Settings";
import { Toaster } from "./ui";

type Tab = "home" | "screens" | "climate" | "settings";

const TABS: { id: Tab; he: string; icon: string }[] = [
  { id: "home", he: "בית", icon: "🏠" },
  { id: "screens", he: "מסכים", icon: "🗂" },
  { id: "climate", he: "מזגן", icon: "❄" },
  { id: "settings", he: "הגדרות", icon: "⚙" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#/", "");
  return (TABS.find((t) => t.id === h)?.id ?? "home") as Tab;
}

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [config, setConfig] = useState<RobotConfig | null>(null);
  const [entities, setEntities] = useState<HAEntity[]>([]);
  const [version, setVersion] = useState("");

  const refreshConfig = useCallback(() => {
    apiGet<RobotConfig>("/api/robot/config").then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    refreshConfig();
    apiGet<Health>("/api/health").then((h) => setVersion(h.version)).catch(() => undefined);
    apiGet<{ entities: HAEntity[] }>("/api/ha/entities")
      .then((r) => setEntities(r.entities))
      .catch(() => undefined);
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, [refreshConfig]);

  function go(t: Tab) {
    window.location.hash = `#/${t}`;
    setTab(t);
  }

  return (
    <div className="mx-auto min-h-dvh max-w-xl">
      {/* header */}
      <header className="flex items-center justify-between px-4 pb-1 pt-4">
        <h1 className="font-display text-2xl">
          דרביקס
          <span dir="ltr" className="ms-2 font-mono text-xs text-mute">
            dravix-os
          </span>
        </h1>
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${config?.online ? "bg-green" : "bg-red"}`}
          title={config?.online ? "מחובר" : "לא מחובר"}
        />
      </header>

      {/* page */}
      <main className="px-4 pb-28 pt-2">
        {tab === "home" && <HomePage config={config} />}
        {tab === "screens" && <ScreensPage entities={entities} />}
        {tab === "climate" && <ClimatePage entities={entities} />}
        {tab === "settings" && (
          <SettingsPage config={config} entities={entities} version={version} onConfigChanged={refreshConfig} />
        )}
      </main>

      {/* bottom tab bar */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-card/95 backdrop-blur"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="mx-auto flex max-w-xl">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => go(t.id)}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs transition ${
                tab === t.id ? "text-teal" : "text-mute"
              }`}
            >
              <span className={`text-xl leading-none ${tab === t.id ? "" : "grayscale opacity-70"}`}>{t.icon}</span>
              {t.he}
              <span
                className={`mt-0.5 h-1 w-8 rounded-full transition ${tab === t.id ? "bg-teal" : "bg-transparent"}`}
              />
            </button>
          ))}
        </div>
      </nav>

      <Toaster />
    </div>
  );
}
