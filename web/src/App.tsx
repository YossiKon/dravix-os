import { useCallback, useEffect, useMemo, useState } from "react";
import { CamerasPanel } from "./components/CamerasPanel";
import { MemoryPanel } from "./components/MemoryPanel";
import { PersonalityPanel } from "./components/PersonalityPanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { Sidebar, type NavItem } from "./components/Sidebar";
import { Toaster } from "./components/Toaster";
import { XiaoZhiPanel } from "./components/XiaoZhiPanel";
import { useDravix } from "./hooks/useDravix";
import { useHasCameras } from "./hooks/useCameras";
import { ToastProvider } from "./hooks/useToasts";
import { useWebSocket } from "./hooks/useWebSocket";
import { CAP, type BusEvent } from "./lib/types";
import { AgentPage } from "./pages/AgentPage";
import { AutomationsPage } from "./pages/AutomationsPage";
import { ScreensPage } from "./pages/ScreensPage";
import { SetupPage } from "./pages/SetupPage";

type PageId =
  | "agent"
  | "personality"
  | "cameras"
  | "automations"
  | "memory"
  | "cloud"
  | "screens"
  | "setup"
  | "settings";

interface PageDef extends NavItem {
  id: PageId;
  /** When false, the page is hidden (capability / config gated). */
  visible: boolean;
}

function Shell() {
  const {
    status,
    statusError,
    modes,
    version,
    loadingStatus,
    loadingModes,
    moodTick,
    refreshStatus,
    refreshModes,
    applyEvent,
  } = useDravix();

  // Feed every WS event into optimistic status updates (stable handler).
  const onEvent = useCallback((e: BusEvent) => applyEvent(e), [applyEvent]);
  const { status: wsStatus, log, clear } = useWebSocket({ onEvent });

  const hasCameras = useHasCameras();

  const refreshAll = useCallback(() => {
    refreshStatus();
    refreshModes();
  }, [refreshStatus, refreshModes]);

  const coreUnreachable = statusError !== null && status === null;
  const caps = new Set(status?.robot.capabilities ?? []);
  const cloudConfigured = status?.xiaozhi?.configured ?? false;

  // ── Capability / config gating: build the visible page list ──────────────
  // The robot exposes take_photo as an extra capability on some backends; either
  // Frigate cameras OR an onboard camera capability unlocks the Cameras page.
  const camerasAvailable = (hasCameras ?? false) || caps.has("take_photo");
  // Personality controls (mood/personas/emotes/voice) only make sense when the
  // robot can express itself — expression, speech, or AI presence.
  const canExpress =
    caps.has(CAP.setFace) || caps.has(CAP.say) || (status?.ai_available ?? false);

  const pages = useMemo<PageDef[]>(
    () => [
      { id: "agent", label: "Agent", icon: "◉", visible: true },
      { id: "personality", label: "Personality", icon: "☺", visible: canExpress },
      { id: "cameras", label: "Cameras", icon: "▣", visible: camerasAvailable },
      { id: "automations", label: "Automations", icon: "⇄", visible: true },
      { id: "memory", label: "Memory", icon: "❏", visible: true },
      { id: "cloud", label: "Cloud", icon: "☁", visible: cloudConfigured },
      // Screens: pick which HA entities show on the robot's 3 display cards.
      { id: "screens", label: "Screens", icon: "▦", visible: true },
      // Setup is always visible — it's how the robot gets configured.
      { id: "setup", label: "Setup", icon: "⛭", visible: true },
      { id: "settings", label: "Settings", icon: "⚙", visible: true },
    ],
    [canExpress, camerasAvailable, cloudConfigured],
  );

  const visiblePages = useMemo(() => pages.filter((p) => p.visible), [pages]);
  const [page, setPage] = useState<PageId>("agent");

  // If the active page becomes hidden (e.g. cloud config removed, capability
  // dropped after telemetry loads), fall back to the Agent hub.
  useEffect(() => {
    if (!visiblePages.some((p) => p.id === page)) setPage("agent");
  }, [visiblePages, page]);

  const navItems: NavItem[] = visiblePages.map(({ id, label, icon }) => ({
    id,
    label,
    icon,
  }));

  return (
    <div className="min-h-screen lg:pl-60">
      <Sidebar
        items={navItems}
        active={page}
        onNavigate={(id) => setPage(id as PageId)}
        status={status}
        version={version}
        wsStatus={wsStatus}
        coreUnreachable={coreUnreachable}
      />

      <main className="relative z-[2] mx-auto max-w-6xl px-4 py-5 sm:px-6 sm:py-7">
        {page === "agent" && (
          <AgentPage
            status={status}
            loadingStatus={loadingStatus}
            statusError={statusError}
            modes={modes}
            loadingModes={loadingModes}
            mood={status?.mood}
            moodTick={moodTick}
            refreshStatus={refreshStatus}
            refreshAll={refreshAll}
            wsStatus={wsStatus}
            log={log}
            clearLog={clear}
          />
        )}

        {page === "personality" && (
          <div className="mx-auto max-w-4xl">
            <PersonalityPanel initialMood={status?.mood} moodTick={moodTick} />
          </div>
        )}

        {page === "cameras" && <CamerasPanel />}

        {page === "automations" && <AutomationsPage />}

        {page === "memory" && (
          <div className="mx-auto max-w-3xl">
            <MemoryPanel />
          </div>
        )}

        {page === "cloud" && (
          <div className="mx-auto max-w-3xl">
            <XiaoZhiPanel xiaozhi={status?.xiaozhi} />
          </div>
        )}

        {page === "screens" && (
          <div className="mx-auto max-w-3xl">
            <ScreensPage />
          </div>
        )}

        {page === "setup" && (
          <div className="mx-auto max-w-3xl">
            <SetupPage />
          </div>
        )}

        {page === "settings" && (
          <div className="mx-auto max-w-3xl">
            <SettingsPanel modes={modes} onModesChanged={refreshModes} />
          </div>
        )}

        <footer className="mt-8 flex flex-wrap items-center justify-between gap-2 border-t border-line/60 pt-4 font-mono text-[10px] uppercase tracking-wider text-mute">
          <span>dravix-os · stackchan companion console</span>
          <span>
            {status?.robot.driver
              ? `driver: ${status.robot.driver}`
              : "awaiting telemetry"}
          </span>
        </footer>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <ToastProvider>
      <Shell />
      <Toaster />
    </ToastProvider>
  );
}
