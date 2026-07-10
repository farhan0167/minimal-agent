import { ToolCallCard, ResultSection, SectionLabel } from "../ToolCallCard";
import { CodeBlock } from "../CodeBlock";
import type { ToolRenderProps } from "../types";

/**
 * edit_file: reconstruct a unified-style diff from the old_string/new_string
 * args and render it with Shiki's diff grammar (removed lines red, added
 * lines green). The args carry everything needed, so the diff shows even
 * while the tool is still running.
 */
function buildDiff(oldString: string, newString: string): string {
  const removed = oldString.split("\n").map((line) => `-${line}`);
  const added = newString.split("\n").map((line) => `+${line}`);
  return [...removed, ...added].join("\n");
}

export function EditFileRenderer({ name, args, result, status }: ToolRenderProps) {
  const filePath = typeof args.file_path === "string" ? args.file_path : "";
  const oldString = typeof args.old_string === "string" ? args.old_string : null;
  const newString = typeof args.new_string === "string" ? args.new_string : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={filePath}>
      {oldString !== null && newString !== null && (
        <div>
          <SectionLabel>Diff</SectionLabel>
          <CodeBlock code={buildDiff(oldString, newString)} language="diff" />
        </div>
      )}
      {status === "error" && <ResultSection result={result} status={status} />}
    </ToolCallCard>
  );
}
