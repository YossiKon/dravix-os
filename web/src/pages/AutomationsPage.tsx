import { ReactionsPanel } from "../components/ReactionsPanel";
import { SchedulePanel } from "../components/SchedulePanel";

/**
 * Automations — event → action reaction rules plus the daily schedule.
 * Both panels are self-contained (fetch + save their own data).
 */
export function AutomationsPage() {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <ReactionsPanel />
      <SchedulePanel />
    </div>
  );
}
