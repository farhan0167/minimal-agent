"""The `read_file` tool — reads a file from the workspace.

Text files come back as numbered lines. Image files (png/jpg/gif/webp) and
PDFs come back multimodally: the tool-result message carries a text pointer,
and the actual image bytes ride a trailing user message the agent loop appends
(the Chat Completions API forbids non-text on a `tool` message). PDFs are
rasterized to one image per page. See
[.claude/specifications/multimodal-tool-results.md](../../../../.claude/specifications/multimodal-tool-results.md).
"""

import time
from pathlib import Path

from ....llm.types import ContentPart, ImagePart, ImageUrl
from ...base import BaseTool
from ...context import ToolContext
from ...results import ValidationErr, ValidationOk, ValidationResult
from .._filesystem import MAX_FILE_SIZE_BYTES, is_path_within
from .helpers import (
    IMAGE_MIME_BY_SUFFIX,
    image_to_data_uri,
    pdf_to_data_uris,
    read_text_content,
)
from .schema import ReadFileInput


class ReadFile(BaseTool[ReadFileInput, dict]):
    name = "read_file"
    input_schema = ReadFileInput
    is_read_only = True

    def __init__(
        self,
        workspace_root: Path,
        read_timestamps: dict[str, float],
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.read_timestamps = read_timestamps

    async def validate(self, args: ReadFileInput, ctx: ToolContext) -> ValidationResult:
        path = Path(args.file_path)

        if not path.is_absolute():
            return ValidationErr("file_path must be an absolute path.")

        if not is_path_within(path, self.workspace_root):
            return ValidationErr(
                f"Path is outside the workspace root ({self.workspace_root})."
            )

        if not path.exists():
            return ValidationErr(f"File not found: {args.file_path}")

        if not path.is_file():
            return ValidationErr(f"Not a file: {args.file_path}")

        # The size guard is text-specific: it exists so an oversized text file
        # is read via offset/limit rather than in one shot. Images/PDFs can't
        # be line-sliced, so the guard (and its advice) doesn't apply to them.
        suffix = path.suffix.lower()
        is_binary_read = suffix == ".pdf" or suffix in IMAGE_MIME_BY_SUFFIX
        if not is_binary_read and args.offset is None and args.limit is None:
            size = path.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                return ValidationErr(
                    f"File is {size:,} bytes (limit: {MAX_FILE_SIZE_BYTES:,}). "
                    f"Use offset/limit to read a portion."
                )

        return ValidationOk()

    async def invoke(self, args: ReadFileInput, ctx: ToolContext) -> dict:
        path = Path(args.file_path)
        suffix = path.suffix.lower()
        self.read_timestamps[str(path.resolve())] = time.time()

        if suffix == ".pdf":
            # May raise PdfSupportUnavailable → dispatcher surfaces it as a
            # tool error the model can read.
            return {
                "kind": "pdf",
                "path": str(path),
                "data_uris": pdf_to_data_uris(path),
            }

        mime = IMAGE_MIME_BY_SUFFIX.get(suffix)
        if mime is not None:
            return {
                "kind": "image",
                "path": str(path),
                "data_uris": [image_to_data_uri(path, mime)],
            }

        result = read_text_content(path, offset=args.offset, limit=args.limit)
        result["kind"] = "text"
        return result

    def render_result_for_assistant(self, out: dict) -> str:
        # For image/PDF the bytes ride the trailing user message the loop
        # appends; this tool-result message is the mandatory text pointer.
        if out["kind"] == "image":
            return f"Read image {out['path']} — attached as the following message."
        if out["kind"] == "pdf":
            n = len(out["data_uris"])
            return (
                f"Read PDF {out['path']} — {n} page(s) rasterized and attached "
                f"as the following message."
            )
        header = (
            f"Lines {out['start_line']}-"
            f"{out['start_line'] + out['num_lines'] - 1} "
            f"of {out['total_lines']} total"
        )
        return f"{header}\n{out['content']}"

    def render_parts_for_assistant(self, out: dict) -> list[ContentPart]:
        if out["kind"] in ("image", "pdf"):
            return [ImagePart(image_url=ImageUrl(url=uri)) for uri in out["data_uris"]]
        return []
