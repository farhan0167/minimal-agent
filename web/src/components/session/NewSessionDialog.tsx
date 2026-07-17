import { useEffect, useMemo, useRef, useState } from "react";
import type { CreateSessionRequest, Session } from "../../types/session";
import { type ServerConfig, getConfig } from "../../api/config";
import { FolderOpen, Plus, X } from "lucide-react";
import { Button } from "../ui/Button";
import { Badge } from "../ui/Badge";

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
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    getConfig().then((cfg) => {
      setConfig(cfg);
      setAgentName(cfg.default_agent ?? cfg.agents[0]?.name ?? null);
    });
  }, []);

  useEffect(() => {
    if (isOpen) {
      dialogRef.current?.showModal();
    } else {
      dialogRef.current?.close();
    }
  }, [isOpen]);

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
        className="px-3 py-2 text-sm bg-app-composer border border-app-border text-app-fg font-serif"
      >
        <Plus className="w-4 h-4" />
        {isCreating && !isOpen ? "Creating..." : "New Session"}
      </Button>

      <dialog
        ref={dialogRef}
        onClose={handleClose}
        className="fixed inset-0 m-auto w-full max-w-md rounded-xl border border-[hsl(var(--claude-border))]
          bg-[hsl(var(--aui-background))] p-0 shadow-[var(--claude-shadow)] backdrop:bg-black/40"
      >
        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-[hsl(var(--aui-foreground))] font-serif">
              New Session
            </h2>
            <Button
              variant="icon"
              size="sm"
              onClick={handleClose}
              title="Close"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>

          {/* Agent picker — only a choice when more than one is registered */}
          {config && config.agents.length > 1 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))]">
                Agent
              </label>
              <select
                value={agentName ?? ""}
                onChange={(e) => setAgentName(e.target.value)}
                className="w-full px-3 py-2 text-sm border border-[hsl(var(--aui-border))] rounded-lg
                  bg-[hsl(var(--claude-composer))] text-[hsl(var(--aui-foreground))]
                  focus:outline-none focus:ring-2 focus:ring-[hsl(var(--aui-ring))]"
                disabled={isCreating}
                autoFocus
              >
                {config.agents.map((a) => (
                  <option key={a.name} value={a.name}>
                    {a.display_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Read-only facts of the selected agent — fixed by the server */}
          {selectedAgent && (
            <div className="flex flex-col gap-2 rounded-lg border border-[hsl(var(--claude-border))] bg-[hsl(var(--claude-composer))] px-3 py-2.5">
              <div className="flex items-center gap-1.5 text-[11px] text-[hsl(var(--aui-muted-foreground))] font-mono">
                <FolderOpen className="w-3 h-3 shrink-0" />
                <span className="truncate">
                  {selectedAgent.workspace_root ?? "no workspace"}
                </span>
              </div>
              <div className="flex flex-wrap gap-1">
                <Badge variant="neutral">{selectedAgent.model}</Badge>
                <Badge variant="accent">{selectedAgent.backend}</Badge>
                <Badge variant="neutral">{selectedAgent.tools.length} tools</Badge>
              </div>
            </div>
          )}

          {error && (
            <p className="text-xs text-[hsl(var(--aui-destructive))] bg-[hsl(var(--aui-destructive)/0.08)] rounded-lg px-3 py-2">
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
      </dialog>
    </>
  );
}
