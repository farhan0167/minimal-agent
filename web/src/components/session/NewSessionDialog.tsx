import { useEffect, useMemo, useState } from "react";
import type { CreateSessionRequest, Session } from "../../types/session";
import { type ServerConfig, getConfig } from "../../api/config";
import { FolderOpen, Plus } from "lucide-react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";
import { Dialog } from "../ui/Dialog";
import { Select } from "../ui/Field";
import { Surface } from "../ui/Surface";
import { Text } from "../ui/Text";

interface NewSessionDialogProps {
  onCreate: (req: CreateSessionRequest) => Promise<Session>;
}

/**
 * "New Session" is zero-friction: the workspace, model, and backend are
 * facts of the server's agent (fetched from /config), not user input.
 * With a single registered agent the button creates immediately; the
 * dialog only appears to pick between multiple agents — or to show an
 * error.
 */
export function NewSessionDialog({ onCreate }: NewSessionDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [agentName, setAgentName] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getConfig().then((cfg) => {
      setConfig(cfg);
      setAgentName(cfg.default_agent ?? cfg.agents[0]?.name ?? null);
    });
  }, []);

  const selectedAgent = useMemo(
    () => config?.agents.find((a) => a.name === agentName) ?? null,
    [config, agentName],
  );

  const handleClose = () => {
    setIsOpen(false);
    setError(null);
  };

  const create = async (agent: string | null) => {
    setIsCreating(true);
    setError(null);
    try {
      await onCreate(agent ? { agent } : {});
      setIsOpen(false);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
      return false;
    } finally {
      setIsCreating(false);
    }
  };

  const handleButtonClick = async () => {
    // Single agent (or config not loaded yet): create straight away and
    // only surface the dialog if something goes wrong.
    if (!config || config.agents.length <= 1) {
      const ok = await create(agentName);
      if (!ok) setIsOpen(true);
      return;
    }
    setIsOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await create(agentName);
  };

  return (
    <>
      <Button
        variant="ghost"
        block
        onClick={handleButtonClick}
        disabled={isCreating}
        className="px-3 py-2 text-sm bg-app-composer border border-app-border text-app-fg"
      >
        <Plus className="w-4 h-4" />
        {isCreating && !isOpen ? "Creating..." : "New Session"}
      </Button>

      <Dialog open={isOpen} onClose={handleClose} title="New Session">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          {/* Agent picker — only a choice when more than one is registered */}
          {config && config.agents.length > 1 && (
            <Select
              label="Agent"
              value={agentName ?? ""}
              onChange={(e) => setAgentName(e.target.value)}
              disabled={isCreating}
            >
              {config.agents.map((a) => (
                <option key={a.name} value={a.name}>
                  {a.display_name}
                </option>
              ))}
            </Select>
          )}

          {/* Read-only facts of the selected agent — fixed by the server */}
          {selectedAgent && (
            <Surface variant="composer" className="flex flex-col gap-2 px-3 py-2.5">
              <Text variant="code" as="div" className="flex items-center gap-1.5">
                <FolderOpen className="w-3 h-3 shrink-0" />
                <span className="truncate">
                  {selectedAgent.workspace_root ?? "no workspace"}
                </span>
              </Text>
              <div className="flex flex-wrap gap-1">
                <Badge variant="neutral">{selectedAgent.model}</Badge>
                <Badge variant="accent">{selectedAgent.backend}</Badge>
                <Badge variant="neutral">{selectedAgent.tools.length} tools</Badge>
              </div>
            </Surface>
          )}

          {error && (
            <p className="text-xs text-app-danger bg-app-danger/10 rounded-ctl px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={handleClose} disabled={isCreating}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              disabled={isCreating || !agentName}
            >
              {isCreating ? "Creating..." : "Create Session"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
