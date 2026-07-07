import { useEffect, useMemo, useRef, useState } from "react";
import type { CreateSessionRequest, Session } from "../../types/session";
import { type ServerConfig, getConfig } from "../../api/config";
import { FolderOpen, Plus, X } from "lucide-react";

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
      <button
        onClick={handleButtonClick}
        disabled={isCreating}
        className="flex items-center justify-center gap-2 w-full px-3 py-2 text-sm
          font-medium text-[hsl(var(--aui-foreground))] bg-[hsl(var(--claude-composer))] border border-[hsl(var(--claude-border))] rounded-lg
          hover:bg-[hsl(var(--claude-hover))] transition-colors font-serif disabled:opacity-50"
      >
        <Plus className="w-4 h-4" />
        {isCreating && !isOpen ? "Creating..." : "New Session"}
      </button>

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
            <button
              type="button"
              onClick={handleClose}
              className="p-1 rounded hover:bg-[hsl(var(--claude-hover))]"
            >
              <X className="w-4 h-4 text-[hsl(var(--aui-muted-foreground))]" />
            </button>
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
                <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium
                  rounded-full bg-[hsl(var(--claude-hover))] text-[hsl(var(--aui-muted-foreground))] border border-[hsl(var(--claude-border))]">
                  {selectedAgent.model}
                </span>
                <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium
                  rounded-full bg-[hsl(var(--aui-primary)/0.06)] text-[hsl(var(--aui-primary))] border border-[hsl(var(--aui-primary)/0.15)]">
                  {selectedAgent.backend}
                </span>
                <span className="inline-flex items-center px-1.5 py-0.5 text-[10px] font-medium
                  rounded-full bg-[hsl(var(--claude-hover))] text-[hsl(var(--aui-muted-foreground))] border border-[hsl(var(--claude-border))]">
                  {selectedAgent.tools.length} tools
                </span>
              </div>
            </div>
          )}

          {error && (
            <p className="text-xs text-[hsl(var(--aui-destructive))] bg-[hsl(var(--aui-destructive)/0.08)] rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-sm font-medium text-[hsl(var(--aui-muted-foreground))]
                rounded-lg hover:bg-[hsl(var(--claude-hover))] transition-colors"
              disabled={isCreating}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isCreating || !agentName}
              className="px-4 py-2 text-sm font-medium text-[hsl(var(--aui-primary-foreground))] bg-[hsl(var(--aui-primary))]
                rounded-lg hover:bg-[hsl(var(--claude-primary-hover))] disabled:opacity-50 transition-colors"
            >
              {isCreating ? "Creating..." : "Create Session"}
            </button>
          </div>
        </form>
      </dialog>
    </>
  );
}
