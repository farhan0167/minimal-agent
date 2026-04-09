"""Input schema for the web_search tool."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class WebSearchInput(BaseModel):
    """Search the web for information using Tavily. Returns relevant
    results with titles, URLs, and content snippets."""

    query: str = Field(..., description="The search query to execute.")
    search_depth: Literal["basic", "advanced"] = Field(
        default="basic",
        description=(
            "'basic' is fast and cheap (1 credit). "
            "'advanced' is slower but more relevant (2 credits)."
        ),
    )
    max_results: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of search results to return.",
    )
    topic: Literal["general", "news"] = Field(
        default="general",
        description=(
            "'general' for broad searches. "
            "'news' for recent events and current affairs."
        ),
    )
    include_answer: bool = Field(
        default=False,
        description="Include an LLM-generated short answer to the query.",
    )
    include_raw_content: bool = Field(
        default=False,
        description="Include the full cleaned content of each result page.",
    )
    time_range: Optional[Literal["day", "week", "month", "year"]] = Field(
        default=None,
        description="Filter results by recency. None for no time filter.",
    )
