// Dravix — remote control for the robot. Tabs: home · screens · life · climate · settings.
import { useCallback, useEffect, useState } from "react";
import { apiGet, apiSend } from "./api";
import type { HAEntity, Health, RobotConfig } from "./api";
import { HomePage } from "./pages/Home";
import { ScreensPage } from "./pages/Screens";
import { VitalsPage } from "./pages/Vitals";
import { ClimatePage } from "./pages/Climate";
import { SettingsPage } from "./pages/Settings";
import { AgentPage } from "./pages/Agent";
import { ControlsPage } from "./pages/Controls";
import { DiagnosticsPage } from "./pages/Diagnostics";
import { Toaster } from "./ui";
import { useI18n } from "./i18n";

type Tab = "home" | "agent" | "screens" | "vitals" | "climate" | "controls" | "diag" | "settings";

const TABS: { id: Tab; he: string; en: string; icon: string }[] = [
  { id: "home", he: "בית", en: "Home", icon: "🏠" },
  { id: "agent", he: "סוכן", en: "Agent", icon: "🤖" },
  { id: "screens", he: "מסכים", en: "Screens", icon: "🗂" },
  { id: "vitals", he: "חיים", en: "Life", icon: "💗" },
  { id: "climate", he: "מזגן", en: "Climate", icon: "❄" },
  { id: "controls", he: "שליטה", en: "Controls", icon: "🕹" },
  { id: "diag", he: "אבחון", en: "Diag", icon: "🩺" },
  { id: "settings", he: "הגדרות", en: "Settings", icon: "⚙" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#/", "");
  return (TABS.find((t) => t.id === h)?.id ?? "home") as Tab;
}

export default function App() {
  const { tr, setLang, nextLang } = useI18n();
  const [tab, setTab] = useState<Tab>(tabFromHash);
  const [config, setConfig] = useState<RobotConfig | null>(null);
  const [entities, setEntities] = useState<HAEntity[]>([]);
  const [version, setVersion] = useState("");

  const refreshConfig = useCallback(() => {
    apiGet<RobotConfig>("/api/robot/config").then(setConfig).catch(() => undefined);
  }, []);

  useEffect(() => {
    // Entities refresh on EVERY 10s tick (not latched on first success) — a robot flashed
    // or renamed while the dashboard is open now shows up without a reload.
    const fetchEntities = () => {
      apiGet<{ entities: HAEntity[] }>("/api/ha/entities")
        .then((r) => setEntities(r.entities))
        .catch(() => undefined);
    };
    const tick = () => {
      refreshConfig();
      apiGet<Health>("/api/health").then((h) => setVersion(h.version)).catch(() => undefined);
      fetchEntities();
    };
    tick();
    // Re-poll while visible so the online dot reflects reality, not just page load.
    const t = setInterval(() => {
      if (document.visibilityState === "visible") tick();
    }, 10000);
    const onFocus = () => fetchEntities();
    window.addEventListener("focus", onFocus);
    const onHash = () => setTab(tabFromHash());
    window.addEventListener("hashchange", onHash);
    return () => {
      clearInterval(t);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("hashchange", onHash);
    };
  }, [refreshConfig]);

  function go(next: Tab) {
    window.location.hash = `#/${next}`;
    setTab(next);
  }

  return (
    <div className="mx-auto min-h-dvh max-w-xl">
      {/* header */}
      <header className="flex items-center justify-between px-4 pb-1 pt-4">
        <h1 className="font-display text-2xl">
          {config?.robot_name || tr("דרביקס", "Dravix")}
          <span dir="ltr" className="ms-2 font-mono text-xs text-mute">
            dravix-os
          </span>
        </h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-full border border-line bg-card2 px-2.5 py-1 text-xs text-mute transition active:scale-95"
            onClick={() => {
              setLang(nextLang.code);
              // keep the SERVER in the same language too (wellness tips, greetings)
              apiSend("/api/config/language", "PUT", { language: nextLang.code }).catch(() => undefined);
            }}
            aria-label={tr("החלף שפה", "Switch language")}
            title={nextLang.label}
          >
            {nextLang.short}
          </button>
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${config?.online ? "bg-green" : "bg-red"}`}
            title={config?.online ? tr("מחובר", "Connected") : tr("לא מחובר", "Offline")}
          />
        </div>
      </header>

      {/* page */}
      <main className="px-4 pb-28 pt-2">
        {tab === "home" && <HomePage config={config} />}
        {tab === "agent" && <AgentPage />}
        {tab === "screens" && <ScreensPage entities={entities} />}
        {tab === "vitals" && <VitalsPage />}
        {tab === "climate" && <ClimatePage entities={entities} />}
        {tab === "controls" && <ControlsPage />}
        {tab === "diag" && <DiagnosticsPage />}
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
          {TABS.map((tb) => (
            <button
              key={tb.id}
              onClick={() => go(tb.id)}
              aria-current={tab === tb.id ? "page" : undefined}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs transition ${
                tab === tb.id ? "text-teal" : "text-mute"
              }`}
            >
              <span className={`text-xl leading-none ${tab === tb.id ? "" : "grayscale opacity-70"}`}>{tb.icon}</span>
              {tr(tb.he, tb.en)}
              <span
                className={`mt-0.5 h-1 w-8 rounded-full transition ${tab === tb.id ? "bg-teal" : "bg-transparent"}`}
              />
            </button>
          ))}
        </div>
      </nav>

      <Toaster />
    </div>
  );
}
