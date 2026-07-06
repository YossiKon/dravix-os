// Dravix — the AI-agent page. Connect your coding agents, watch what they're doing, and
// approve or reject the tools they ask to run (the robot shows the most urgent one on its face).
import { AgentCard } from "../components/AgentCard";
import { useI18n } from "../i18n";

export function AgentPage() {
  const { tr } = useI18n();
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-display text-xl">{tr("🤖 סוכן AI", "🤖 AI agent")}</h2>
        <p className="mt-1 text-sm text-mute">
          {tr(
            "חבר סוכני AI (Claude Code וכו') מהמחשב, עקוב אחרי מה שהם עושים, ואשר או דחה כלים שהם מבקשים להריץ. אישורים מופיעים גם על מסך הרובוט.",
            "Connect AI agents (Claude Code, etc.) from your PC, watch what they're doing, and approve or reject the tools they ask to run. Requests also pop up on the robot's screen.",
          )}
        </p>
      </div>
      <AgentCard />
    </div>
  );
}
