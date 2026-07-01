import type { WsStatus } from "../hooks/useWebSocket";
import type { BusEvent, Mood, ModeInfo, StatusResponse } from "../lib/types";
import { CapabilitiesPanel } from "../components/CapabilitiesPanel";
import { CloudStatus } from "../components/CloudStatus";
import { EventsLog } from "../components/EventsLog";
import { ManualControl } from "../components/ManualControl";
import { ModesPanel } from "../components/ModesPanel";
import { MoodMeters } from "../components/MoodMeters";
import { PowerModeControl } from "../components/PowerModeControl";
import { StatusPanel } from "../components/StatusPanel";
import { TalkPanel } from "../components/TalkPanel";

/**
 * Agent — the live, real-time control + telemetry hub (default page).
 *
 * Everything here is driven by the shared status poll (4s) and the /ws/events
 * WebSocket stream; no page-local pollers are added. Controls are
 * capability-gated inside their panels (ManualControl / TalkPanel) so the page
 * degrades gracefully across mock / partial-HA / full-MCP backends.
 */
export function AgentPage({
  status,
  loadingStatus,
  statusError,
  modes,
  loadingModes,
  mood,
  moodTick,
  refreshStatus,
  refreshAll,
  wsStatus,
  log,
  clearLog,
}: {
  status: StatusResponse | null;
  loadingStatus: boolean;
  statusError: string | null;
  modes: ModeInfo[];
  loadingModes: boolean;
  mood?: Mood;
  moodTick: number;
  refreshStatus: () => void;
  refreshAll: () => void;
  wsStatus: WsStatus;
  log: BusEvent[];
  clearLog: () => void;
}) {
  const capabilities = status?.robot.capabilities ?? [];
  const cloudConfigured = status?.xiaozhi?.configured ?? false;

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
      {/* Main column: telemetry + live control */}
      <div className="space-y-5 xl:col-span-2">
        <StatusPanel status={status} loading={loadingStatus} error={statusError} />

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <CapabilitiesPanel capabilities={capabilities} ready={status !== null} />
          {mood ? (
            <MoodMeters initialMood={mood} moodTick={moodTick} />
          ) : (
            <ModesSlot
              modes={modes}
              activeMode={status?.active_mode ?? null}
              loading={loadingModes}
              onChanged={refreshAll}
            />
          )}
        </div>

        {/* Sleep now / Wake — only shows when a mode_select entity is mapped */}
        <PowerModeControl />

        {/* Live actuator control — joystick head pad + face/leds/say, gated */}
        <ManualControl status={status} onRefresh={refreshStatus} />

        {/* Say + AI chat (capability / ai_available gated internally) */}
        <TalkPanel status={status} />

        {/* If mood took the grid slot above, modes render full-width here */}
        {mood && (
          <ModesPanel
            modes={modes}
            activeMode={status?.active_mode ?? null}
            loading={loadingModes}
            onChanged={refreshAll}
          />
        )}

        {cloudConfigured && status?.xiaozhi && (
          <CloudStatus xiaozhi={status.xiaozhi} />
        )}
      </div>

      {/* Side column: live event feed, sticky on desktop */}
      <div className="xl:col-span-1">
        <div className="xl:sticky xl:top-4">
          <EventsLog log={log} status={wsStatus} onClear={clearLog} />
        </div>
      </div>
    </div>
  );
}

// Thin wrapper so modes can occupy the mood grid slot when no mood is present.
function ModesSlot(props: {
  modes: ModeInfo[];
  activeMode: string | null;
  loading: boolean;
  onChanged: () => void;
}) {
  return <ModesPanel {...props} />;
}
