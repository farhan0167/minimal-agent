"""Read-specific helpers: text content reading with line numbers, plus
image/PDF rasterization into base64 data URIs for multimodal reads."""

import base64
import io
from pathlib import Path

# Extensions we send to the model as images (data-URI mime by suffix).
IMAGE_MIME_BY_SUFFIX: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class PdfSupportUnavailable(RuntimeError):
    """Raised when a PDF read is requested but `pdf2image` isn't installed."""


def image_to_data_uri(file_path: Path, mime: str) -> str:
    """Read an image file and encode it as a base64 data URI."""
    data = base64.b64encode(file_path.read_bytes()).decode()
    return f"data:{mime};base64,{data}"


def pdf_to_data_uris(file_path: Path) -> list[str]:
    """Rasterize a PDF to one PNG data URI per page.

    Mirrors `example/server`'s attachment handling so read-PDFs and uploaded
    PDFs reach the model identically. `pdf2image` (and system poppler) is an
    optional dependency — absence raises PdfSupportUnavailable rather than a
    bare ImportError, so the dispatcher surfaces a clear message to the model.
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError as e:  # pragma: no cover - exercised via monkeypatch
        raise PdfSupportUnavailable(
            "Reading PDF files requires the 'pdf2image' package (and system "
            "poppler), which is not installed."
        ) from e

    uris: list[str] = []
    for page_img in convert_from_bytes(file_path.read_bytes()):
        buf = io.BytesIO()
        page_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        uris.append(f"data:image/png;base64,{b64}")
    return uris


def read_text_content(
    file_path: Path,
    offset: int | None = None,
    limit: int | None = None,
) -> dict:
    """Read a text file and return its content with line metadata.

    Lines are formatted with `cat -n` style numbering (1-indexed, 6-char
    padded, tab-separated). The model depends on this format to reference
    specific lines in follow-up requests.
    """
    text = file_path.read_text(encoding="utf-8")
    all_lines = text.splitlines()
    total_lines = len(all_lines)

    start = offset or 0
    end = (start + limit) if limit else total_lines
    selected = all_lines[start:end]

    numbered = []
    for i, line in enumerate(selected, start=start + 1):
        numbered.append(f"{i:>6}\t{line}")

    return {
        "content": "\n".join(numbered),
        "num_lines": len(selected),
        "total_lines": total_lines,
        "start_line": start + 1,
    }
