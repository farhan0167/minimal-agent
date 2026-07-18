import { ToolCallCard, ResultSection, SectionLabel } from "../ToolCallCard";
import { DiffViewer } from "../../ui/DiffViewer";
import type { ToolRenderProps } from "../types";

/**
 * edit_file: render a real line diff of the old_string/new_string args with
 * DiffViewer — unchanged context lines stay quiet, only actual changes get
 * the add/del treatment. The args carry everything needed, so the diff shows
 * even while the tool is still running.
 *
 * Line numbers are off: the args are a fragment of the file, so numbering
 * would start at 1 and mislead. The card's subtitle already names the file,
 * so the header stays off too.
 */
export function EditFileRenderer({ name, args, result, status }: ToolRenderProps) {
  const filePath = typeof args.file_path === "string" ? args.file_path : "";
  const oldString = typeof args.old_string === "string" ? args.old_string : null;
  const newString = typeof args.new_string === "string" ? args.new_string : null;

  return (
    <ToolCallCard name={name} status={status} subtitle={filePath}>
      {oldString !== null && newString !== null && (
        <div>
          <SectionLabel>Diff</SectionLabel>
          <DiffViewer
            oldFile={{ content: oldString }}
            newFile={{ content: newString }}
            showLineNumbers={false}
          />
        </div>
      )}
      {status === "error" && <ResultSection result={result} status={status} />}
    </ToolCallCard>
  );
}
