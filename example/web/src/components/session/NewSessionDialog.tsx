import { useEffect, useRef, useState } from "react";
import type { CreateSessionRequest, Session } from "../../types/session";
import { Plus, X } from "lucide-react";

interface NewSessionDialogProps {
  onCreate: (req: CreateSessionRequest) => Promise<Session>;
}

export function NewSessionDialog({ onCreate }: NewSessionDialogProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [workspacePath, setWorkspacePath] = useState("");
  const [model, setModel] = useState("");
  const [backend, setBackend] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (isOpen) {
      dialogRef.current?.showModal();
    } else {
      dialogRef.current?.close();
    }
  }, [isOpen]);

  const handleClose = () => {
    setIsOpen(false);
    setError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!workspacePath.trim()) return;

    setIsCreating(true);
    setError(null);

    try {
      const req: CreateSessionRequest = {
        workspace_root: workspacePath.trim(),
      };
      if (model.trim()) req.model = model.trim();
      if (backend.trim()) req.backend = backend.trim();

      await onCreate(req);
      setWorkspacePath("");
      setModel("");
      setBackend("");
      setIsOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create session");
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex items-center justify-center gap-2 w-full px-3 py-2 text-sm
          font-medium text-[hsl(var(--aui-foreground))] bg-[hsl(var(--claude-composer))] border border-[hsl(var(--claude-border))] rounded-lg
          hover:bg-[hsl(var(--claude-hover))] transition-colors font-serif"
      >
        <Plus className="w-4 h-4" />
        New Session
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

          {/* Workspace */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))]">
              Workspace Path <span className="text-[hsl(var(--aui-destructive))]">*</span>
            </label>
            <input
              type="text"
              value={workspacePath}
              onChange={(e) => setWorkspacePath(e.target.value)}
              placeholder="/absolute/path/to/project"
              className="w-full px-3 py-2 text-sm border border-[hsl(var(--aui-border))] rounded-lg
                bg-[hsl(var(--claude-composer))] text-[hsl(var(--aui-foreground))]
                focus:outline-none focus:ring-2 focus:ring-[hsl(var(--aui-ring))]"
              autoFocus
              disabled={isCreating}
            />
          </div>

          {/* Model */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))]">
              Model{" "}
              <span className="text-[hsl(var(--aui-muted-foreground))] font-normal opacity-70">
                (optional — uses server default)
              </span>
            </label>
            <input
              type="text"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="e.g. gpt-4o, claude-sonnet-4-20250514"
              className="w-full px-3 py-2 text-sm border border-[hsl(var(--aui-border))] rounded-lg
                bg-[hsl(var(--claude-composer))] text-[hsl(var(--aui-foreground))]
                focus:outline-none focus:ring-2 focus:ring-[hsl(var(--aui-ring))]"
              disabled={isCreating}
            />
          </div>

          {/* Backend */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-[hsl(var(--aui-muted-foreground))]">
              Backend{" "}
              <span className="text-[hsl(var(--aui-muted-foreground))] font-normal opacity-70">
                (optional — uses server default)
              </span>
            </label>
            <select
              value={backend}
              onChange={(e) => setBackend(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-[hsl(var(--aui-border))] rounded-lg
                bg-[hsl(var(--claude-composer))] text-[hsl(var(--aui-foreground))]
                focus:outline-none focus:ring-2 focus:ring-[hsl(var(--aui-ring))]"
              disabled={isCreating}
            >
              <option value="">Server default</option>
              <option value="openai">OpenAI</option>
              <option value="anthropic">Anthropic</option>
              <option value="openrouter">OpenRouter</option>
              <option value="localhost">Localhost</option>
            </select>
          </div>

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
              disabled={isCreating || !workspacePath.trim()}
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
