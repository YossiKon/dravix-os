// Dravix — remote control for the robot. Tabs: home · screens · life · climate · settings.
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "./api";
import type { HAEntity, Health, RobotConfig } from "./api";
import { HomePage } from "./pages/Home";
import { ScreensPage } from "./pages/Screens";
import { VitalsPage } from "./pages/Vitals";
import { ClimatePage } from "./pages/Climate";
import { SettingsPage } from "./pages/Settings";
import { Toaster } from "./ui";
import { useI18n } from "./i18n";

type Tab = "home" | "screens" | "vitals" | "climate" | "settings";

const TABS: { id: Tab; he: string; en: string; icon: string }[] = [
  { id: "home", he: "בית", en: "Home", icon: "🏠" },
  { id: "screens", he: "מסכים", en: "Screens", icon: "🗂" },
  { id: "vitals", he: "חיים", en: "Life", icon: "💗" },
  { id: "climate", he: "מזגן", en: "Climate", icon: "❄" },
  { id: "settings", he: "הגדרות", en: "Settings", icon: "⚙" },
];

function tabFromHash(): Tab {
  const h = window.location.hash.replace("#/", "");
  return (TABS.find((t) => t.id === h)?.id ?? "home") as Tab;
}

export default function App() {
  const { tr, lang, setLang } = useI18n();
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

  function go(next: Tab) {
    window.location.hash = `#/${next}`;
    setTab(next);
  }

  return (
    <div className="mx-auto min-h-dvh max-w-xl">
      {/* header */}
      <header className="flex items-center justify-between px-4 pb-1 pt-4">
        <h1 className="font-display text-2xl">
          {tr("דרביקס", "Dravix")}
          <span dir="ltr" className="ms-2 font-mono text-xs text-mute">
            dravix-os
          </span>
        </h1>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded-full border border-line bg-card2 px-2.5 py-1 text-xs text-mute transition active:scale-95"
            onClick={() => setLang(lang === "he" ? "en" : "he")}
            aria-label="Switch language"
            title={lang === "he" ? "English" : "עברית"}
          >
            {lang === "he" ? "EN" : "עב"}
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
        {tab === "screens" && <ScreensPage entities={entities} />}
        {tab === "vitals" && <VitalsPage />}
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
          {TABS.map((tb) => (
            <button
              key={tb.id}
              onClick={() => go(tb.id)}
              className={`flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs transition ${
                tab === tb.id ? "text-teal" : "text-mute"
              }`}
            >
              <span className={`text-xl leading-none ${tab === tb.id ? "" : "grayscale opacity-70"}`}>{tb.icon}</span>
              {lang === "en" ? tb.en : tb.he}
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
