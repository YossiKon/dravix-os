import { useCallback, useState } from "react";
import { CamerasPanel } from "./components/CamerasPanel";
import { CapabilitiesPanel } from "./components/CapabilitiesPanel";
import { EventsLog } from "./components/EventsLog";
import { Header } from "./components/Header";
import { ManualControl } from "./components/ManualControl";
import { MemoryPanel } from "./components/MemoryPanel";
import { ModesPanel } from "./components/ModesPanel";
import { PersonalityPanel } from "./components/PersonalityPanel";
import { ReactionsPanel } from "./components/ReactionsPanel";
import { SchedulePanel } from "./components/SchedulePanel";
import { SettingsPanel } from "./components/SettingsPanel";
import { StatusPanel } from "./components/StatusPanel";
import { TalkPanel } from "./components/TalkPanel";
import { Toaster } from "./components/Toaster";
import { XiaoZhiPanel } from "./components/XiaoZhiPanel";
import { Tabs, type TabDef } from "./components/ui";
import { useDravix } from "./hooks/useDravix";
import { ToastProvider } from "./hooks/useToasts";
import { useWebSocket } from "./hooks/useWebSocket";
import type { BusEvent } from "./lib/types";

type TabId =
  | "console"
  | "personality"
  | "cameras"
  | "reactions"
  | "schedule"
  | "memory"
  | "settings";

const TABS: TabDef[] = [
  { id: "console", label: "Console" },
  { id: "personality", label: "Personality" },
  { id: "cameras", label: "Cameras" },
  { id: "reactions", label: "Reactions" },
  { id: "schedule", label: "Schedule" },
  { id: "memory", label: "Memory" },
  { id: "settings", label: "Settings" },
];

function Console() {
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

  const [tab, setTab] = useState<TabId>("console");

  // Stable handler: feed every WS event into optimistic status updates.
  const onEvent = useCallback((e: BusEvent) => applyEvent(e), [applyEvent]);
  const { status: wsStatus, log, clear } = useWebSocket({ onEvent });

  const refreshAll = useCallback(() => {
    refreshStatus();
    refreshModes();
  }, [refreshStatus, refreshModes]);

  const capabilities = status?.robot.capabilities ?? [];

  return (
    <div className="relative z-[2] min-h-screen">
      <Header
        status={status}
        version={version}
        wsStatus={wsStatus}
        statusError={statusError !== null && status === null}
      />

      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Tabs
          tabs={TABS}
          active={tab}
          onChange={(id) => setTab(id as TabId)}
          className="mb-5"
        />

        {tab === "console" && (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {/* Left rail: status + capabilities + modes */}
            <div className="space-y-5 lg:col-span-2">
              <StatusPanel
                status={status}
                loading={loadingStatus}
                error={statusError}
              />
              <CapabilitiesPanel
                capabilities={capabilities}
                ready={status !== null}
              />
              <ModesPanel
                modes={modes}
                activeMode={status?.active_mode ?? null}
                loading={loadingModes}
                onChanged={refreshAll}
              />
              <ManualControl status={status} onRefresh={refreshStatus} />
              <TalkPanel status={status} />
              <XiaoZhiPanel xiaozhi={status?.xiaozhi} />
            </div>

            {/* Right rail: live events (sticky on desktop) */}
            <div className="lg:col-span-1">
              <div className="lg:sticky lg:top-[88px]">
                <EventsLog log={log} status={wsStatus} onClear={clear} />
              </div>
            </div>
          </div>
        )}

        {tab === "personality" && (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <PersonalityPanel
                initialMood={status?.mood}
                moodTick={moodTick}
              />
            </div>
            <div className="lg:col-span-1">
              <div className="lg:sticky lg:top-[88px]">
                <EventsLog log={log} status={wsStatus} onClear={clear} />
              </div>
            </div>
          </div>
        )}

        {tab === "cameras" && <CamerasPanel />}

        {tab === "reactions" && (
          <div className="mx-auto max-w-3xl">
            <ReactionsPanel />
          </div>
        )}

        {tab === "schedule" && (
          <div className="mx-auto max-w-3xl">
            <SchedulePanel />
          </div>
        )}

        {tab === "memory" && (
          <div className="mx-auto max-w-3xl">
            <MemoryPanel />
          </div>
        )}

        {tab === "settings" && (
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
      <Console />
      <Toaster />
    </ToastProvider>
  );
}
