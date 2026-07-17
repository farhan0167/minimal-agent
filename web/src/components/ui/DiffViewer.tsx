import { type ComponentProps, useMemo } from "react";
import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { diffLines } from "diff";
import parseDiff from "parse-diff";

/**
 * The diff.
 *
 * Renders code changes — a unified `git diff` patch, or an old/new content
 * pair — with per-line add/del grounds, line numbers, and an optional
 * file header with +/− stats, in unified or split view.
 *
 * Adapted from assistant-ui's registry DiffViewer (a standalone component
 * with no runtime dependency): cva and `cn` are replaced with this
 * codebase's plain-Record variant idiom, and every hardcoded GitHub
 * green/red is replaced with the semantic tokens — added lines compose
 * --app-success with alpha, deleted lines --app-danger, exactly as
 * ToolCallCard tints its error ground. No new roles: a theme that answers
 * "success" and "danger" has already answered "diff".
 *
 * It accepts SyntaxHighlighterProps so it can also be registered for
 * ```diff fences via MarkdownText's componentsByLanguage.
 */

type DiffLineType = "add" | "del" | "normal";

interface ParsedLine {
  type: DiffLineType;
  content: string;
  oldLineNumber?: number;
  newLineNumber?: number;
}

interface ParsedFile {
  oldName?: string | undefined;
  newName?: string | undefined;
  lines: ParsedLine[];
  additions: number;
  deletions: number;
}

interface SplitLinePair {
  left: ParsedLine | null;
  right: ParsedLine | null;
}

function parsePatch(patch: string): ParsedFile[] {
  const files = parseDiff(patch);
  return files.map((file) => {
    const lines: ParsedLine[] = [];
    let additions = 0;
    let deletions = 0;
    for (const chunk of file.chunks) {
      let oldLine = chunk.oldStart;
      let newLine = chunk.newStart;
      for (const change of chunk.changes) {
        if (change.type === "add") {
          additions++;
          lines.push({
            type: "add",
            content: change.content.slice(1),
            newLineNumber: newLine++,
          });
        } else if (change.type === "del") {
          deletions++;
          lines.push({
            type: "del",
            content: change.content.slice(1),
            oldLineNumber: oldLine++,
          });
        } else {
          lines.push({
            type: "normal",
            content: change.content.slice(1),
            oldLineNumber: oldLine++,
            newLineNumber: newLine++,
          });
        }
      }
    }
    return {
      oldName: file.from,
      newName: file.to,
      lines,
      additions,
      deletions,
    };
  });
}

function computeDiff(
  oldContent: string,
  newContent: string,
): { lines: ParsedLine[]; additions: number; deletions: number } {
  const changes = diffLines(oldContent, newContent);
  const lines: ParsedLine[] = [];
  let oldLine = 1;
  let newLine = 1;
  let additions = 0;
  let deletions = 0;

  for (const change of changes) {
    const contentLines = change.value.replace(/\n$/, "").split("\n");
    for (const content of contentLines) {
      if (change.added) {
        additions++;
        lines.push({ type: "add", content, newLineNumber: newLine++ });
      } else if (change.removed) {
        deletions++;
        lines.push({ type: "del", content, oldLineNumber: oldLine++ });
      } else {
        lines.push({
          type: "normal",
          content,
          oldLineNumber: oldLine++,
          newLineNumber: newLine++,
        });
      }
    }
  }
  return { lines, additions, deletions };
}

function pairLinesForSplit(lines: ParsedLine[]): SplitLinePair[] {
  const pairs: SplitLinePair[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i]!;
    if (line.type === "normal") {
      pairs.push({ left: line, right: line });
      i++;
    } else if (line.type === "del") {
      const deletions: ParsedLine[] = [];
      while (i < lines.length && lines[i]!.type === "del") {
        deletions.push(lines[i]!);
        i++;
      }
      const additions: ParsedLine[] = [];
      while (i < lines.length && lines[i]!.type === "add") {
        additions.push(lines[i]!);
        i++;
      }
      const maxLen = Math.max(deletions.length, additions.length);
      for (let j = 0; j < maxLen; j++) {
        pairs.push({
          left: deletions[j] ?? null,
          right: additions[j] ?? null,
        });
      }
    } else {
      pairs.push({ left: null, right: line });
      i++;
    }
  }
  return pairs;
}

const join = (...classes: (string | false | undefined)[]) =>
  classes.filter(Boolean).join(" ");

export type DiffViewerVariant = "default" | "ghost" | "muted";
export type DiffViewerSize = "sm" | "default" | "lg";

const CONTAINER: Record<DiffViewerVariant, string> = {
  default: "bg-app-surface border border-app-border",
  ghost: "bg-transparent",
  muted: "bg-app-hover border border-app-border-subtle",
};

const SIZES: Record<DiffViewerSize, string> = {
  sm: "text-xs",
  default: "text-sm",
  lg: "text-base",
};

// The line's ground tints its host (alpha-composed semantic tokens); the
// line's text takes the full-strength role.
const LINE_BG: Record<DiffLineType | "empty", string> = {
  add: "bg-app-success/15",
  del: "bg-app-danger/10",
  normal: "",
  empty: "",
};

const LINE_TEXT: Record<DiffLineType | "empty", string> = {
  add: "text-app-success",
  del: "text-app-danger",
  normal: "",
  empty: "",
};

function getFileExtension(filename?: string): string {
  const ext = filename?.split(".").pop()?.toLowerCase();
  if (!ext) return "";
  return ext.toUpperCase();
}

function DiffViewerFileBadge({ filename }: { filename?: string | undefined }) {
  const ext = getFileExtension(filename);
  if (!ext) return null;

  return (
    <span
      data-slot="diff-viewer-file-badge"
      className="bg-app-surface border border-app-border rounded-badge inline-flex size-5 shrink-0 items-end justify-end text-[8px] leading-none font-bold"
    >
      <span className="p-0.5">{ext}</span>
    </span>
  );
}

function DiffViewerStats({
  additions,
  deletions,
}: {
  additions: number;
  deletions: number;
}) {
  return (
    <span data-slot="diff-viewer-stats" className="flex gap-2 text-xs">
      <span className="text-app-success">+{additions}</span>
      <span className="text-app-danger">-{deletions}</span>
    </span>
  );
}

interface DiffViewerHeaderProps extends ComponentProps<"div"> {
  oldName?: string | undefined;
  newName?: string | undefined;
  additions?: number;
  deletions?: number;
  showIcon?: boolean;
  showStats?: boolean;
}

function DiffViewerHeader({
  oldName,
  newName,
  additions = 0,
  deletions = 0,
  showIcon = true,
  showStats = true,
  className,
  ...props
}: DiffViewerHeaderProps) {
  if (!oldName && !newName) return null;

  const displayName = newName || oldName;

  return (
    <div
      data-slot="diff-viewer-header"
      className={join(
        "bg-app-hover text-app-fg-muted border-b border-app-border flex items-center gap-2 px-4 py-2 font-ui",
        className,
      )}
      {...props}
    >
      {showIcon && <DiffViewerFileBadge filename={displayName} />}
      <span className="flex-1 truncate">
        {oldName && newName && oldName !== newName ? (
          <>
            <span className="text-app-danger">{oldName}</span>
            {" → "}
            <span className="text-app-success">{newName}</span>
          </>
        ) : (
          displayName
        )}
      </span>
      {showStats && (additions > 0 || deletions > 0) && (
        <DiffViewerStats additions={additions} deletions={deletions} />
      )}
    </div>
  );
}

interface DiffViewerLineProps extends ComponentProps<"div"> {
  line: ParsedLine;
  showLineNumbers?: boolean;
}

function DiffViewerLine({
  line,
  showLineNumbers = true,
  className,
  ...props
}: DiffViewerLineProps) {
  const indicator = line.type === "add" ? "+" : line.type === "del" ? "-" : " ";

  return (
    <div
      data-slot="diff-viewer-line"
      data-type={line.type}
      className={join("flex", LINE_BG[line.type], className)}
      {...props}
    >
      {showLineNumbers && (
        <span
          data-slot="diff-viewer-line-number"
          className="text-app-fg-muted w-12 shrink-0 px-2 text-end select-none"
        >
          {line.type === "del"
            ? line.oldLineNumber
            : line.type === "add"
              ? line.newLineNumber
              : line.oldLineNumber}
        </span>
      )}
      <span
        data-slot="diff-viewer-indicator"
        className={join(
          "w-4 shrink-0 text-center select-none",
          LINE_TEXT[line.type],
        )}
      >
        {indicator}
      </span>
      <span
        data-slot="diff-viewer-content"
        className={join(
          "flex-1 break-all whitespace-pre-wrap",
          LINE_TEXT[line.type],
        )}
      >
        {line.content}
      </span>
    </div>
  );
}

interface DiffViewerSplitLineProps extends ComponentProps<"div"> {
  pair: SplitLinePair;
  showLineNumbers?: boolean;
}

function DiffViewerSplitLine({
  pair,
  showLineNumbers = true,
  className,
  ...props
}: DiffViewerSplitLineProps) {
  const { left, right } = pair;

  return (
    <div
      data-slot="diff-viewer-split-line"
      className={join("flex", className)}
      {...props}
    >
      <div
        data-slot="diff-viewer-split-left"
        data-type={left?.type ?? "empty"}
        className={join(
          "flex w-1/2 border-e border-app-border",
          LINE_BG[left?.type ?? "empty"],
        )}
      >
        {showLineNumbers && (
          <span className="text-app-fg-muted w-12 shrink-0 px-2 text-end select-none">
            {left?.oldLineNumber ?? ""}
          </span>
        )}
        <span
          className={join(
            "w-4 shrink-0 text-center select-none",
            LINE_TEXT[left?.type ?? "empty"],
          )}
        >
          {left ? (left.type === "del" ? "-" : " ") : ""}
        </span>
        <span
          className={join(
            "flex-1 break-all whitespace-pre-wrap",
            LINE_TEXT[left?.type ?? "empty"],
          )}
        >
          {left?.content ?? ""}
        </span>
      </div>
      <div
        data-slot="diff-viewer-split-right"
        data-type={right?.type ?? "empty"}
        className={join("flex w-1/2", LINE_BG[right?.type ?? "empty"])}
      >
        {showLineNumbers && (
          <span className="text-app-fg-muted w-12 shrink-0 px-2 text-end select-none">
            {right?.newLineNumber ?? ""}
          </span>
        )}
        <span
          className={join(
            "w-4 shrink-0 text-center select-none",
            LINE_TEXT[right?.type ?? "empty"],
          )}
        >
          {right ? (right.type === "add" ? "+" : " ") : ""}
        </span>
        <span
          className={join(
            "flex-1 break-all whitespace-pre-wrap",
            LINE_TEXT[right?.type ?? "empty"],
          )}
        >
          {right?.content ?? ""}
        </span>
      </div>
    </div>
  );
}

export type DiffViewerProps = Partial<SyntaxHighlighterProps> & {
  patch?: string;
  oldFile?: { content: string; name?: string };
  newFile?: { content: string; name?: string };
  viewMode?: "split" | "unified";
  showLineNumbers?: boolean;
  showIcon?: boolean;
  showStats?: boolean;
  variant?: DiffViewerVariant;
  size?: DiffViewerSize;
  /** Layout only. */
  className?: string;
};

export function DiffViewer({
  code,
  patch,
  oldFile,
  newFile,
  viewMode = "unified",
  showLineNumbers = true,
  showIcon = true,
  showStats = true,
  variant = "default",
  size = "default",
  className,
}: DiffViewerProps) {
  const diffPatch = patch ?? code;
  const oldContent = oldFile?.content;
  const oldName = oldFile?.name;
  const newContent = newFile?.content;
  const newName = newFile?.name;

  const parsedFiles = useMemo<ParsedFile[]>(() => {
    if (diffPatch) {
      return parsePatch(diffPatch);
    }
    if (oldContent !== undefined && newContent !== undefined) {
      const { lines, additions, deletions } = computeDiff(
        oldContent,
        newContent,
      );
      return [
        {
          oldName,
          newName,
          lines,
          additions,
          deletions,
        },
      ];
    }
    return [];
  }, [diffPatch, oldContent, oldName, newContent, newName]);

  const splitLinePairs = useMemo<SplitLinePair[][]>(() => {
    if (viewMode !== "split") return [];
    return parsedFiles.map((file) => pairLinesForSplit(file.lines));
  }, [parsedFiles, viewMode]);

  if (parsedFiles.length === 0) {
    return (
      <pre
        data-slot="diff-viewer"
        className={join(
          "bg-app-hover text-app-fg-muted rounded-surface p-4 font-mono",
          className,
        )}
      >
        No diff content provided
      </pre>
    );
  }

  return (
    <div
      data-slot="diff-viewer"
      data-view-mode={viewMode}
      data-variant={variant}
      data-size={size}
      className={join(
        "overflow-hidden rounded-surface font-mono",
        CONTAINER[variant],
        SIZES[size],
        className,
      )}
    >
      {parsedFiles.map((file, fileIndex) => (
        <div
          key={fileIndex}
          data-slot="diff-viewer-file"
          // Long diffs render lazily as they scroll into view.
          className="[contain-intrinsic-size:auto_240px] [content-visibility:auto]"
        >
          <DiffViewerHeader
            oldName={file.oldName}
            newName={file.newName}
            additions={file.additions}
            deletions={file.deletions}
            showIcon={showIcon}
            showStats={showStats}
          />
          <div data-slot="diff-viewer-content" className="overflow-x-auto py-1">
            {viewMode === "split"
              ? (splitLinePairs[fileIndex] ?? []).map((pair, pairIndex) => (
                  <DiffViewerSplitLine
                    key={pairIndex}
                    pair={pair}
                    showLineNumbers={showLineNumbers}
                  />
                ))
              : file.lines.map((line, lineIndex) => (
                  <DiffViewerLine
                    key={lineIndex}
                    line={line}
                    showLineNumbers={showLineNumbers}
                  />
                ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export type { ParsedLine, ParsedFile, SplitLinePair };
