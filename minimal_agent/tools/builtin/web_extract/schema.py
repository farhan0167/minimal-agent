"""Input schema for the web_extract tool."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WebExtractInput(BaseModel):
    """Extract the full content of one or more web pages using Tavily Extract.
    Use this after web_search to read a page in detail."""

    urls: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="URLs to extract content from (1-10).",
    )
    extract_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description=(
            "'basic' is fast (1 credit per 5 URLs). "
            "'advanced' retrieves more data including tables (2 credits per 5 URLs)."
        ),
    )
    format: Literal["markdown", "text"] = Field(
        default="markdown",
        description="Output format for extracted content.",
    )
    query: Optional[str] = Field(
        default=None,
        description=(
            "Optional query to rerank extracted content by relevance. "
            "When set, content is chunked and ranked by this query."
        ),
    )
