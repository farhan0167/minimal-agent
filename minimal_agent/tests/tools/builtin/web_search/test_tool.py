"""Tests for the ``web_search`` builtin tool."""

from unittest.mock import AsyncMock, patch

from tools import ToolContext
from tools.builtin.web_search import WebSearch, WebSearchInput


def test_metadata():
    assert WebSearch.name == "web_search"
    assert WebSearch.is_read_only is True
    assert WebSearch.input_schema is WebSearchInput


def test_as_llm_tool_schema():
    wire = WebSearch.as_llm_tool()
    assert wire.name == "web_search"
    assert "search" in wire.description.lower()
    assert "query" in wire.parameters["required"]


def test_needs_permission():
    tool = WebSearch()
    args = WebSearchInput(query="test")
    assert tool.needs_permission(args) is True


def test_permission_description_short_query():
    tool = WebSearch()
    args = WebSearchInput(query="python asyncio")
    desc = tool.permission_description(args)
    assert "Web search:" in desc
    assert "python asyncio" in desc


def test_permission_description_long_query():
    tool = WebSearch()
    long_query = "a" * 100
    args = WebSearchInput(query=long_query)
    desc = tool.permission_description(args)
    assert len(desc) < 120
    assert desc.endswith("...")


@patch("tools.builtin.web_search.tool.tavily_request", new_callable=AsyncMock)
async def test_invoke_sends_correct_payload(mock_request):
    mock_request.return_value = {"results": [], "answer": None}

    tool = WebSearch()
    args = WebSearchInput(query="who is messi", max_results=3, topic="general")
    await tool.invoke(args, ToolContext())

    mock_request.assert_awaited_once()
    call_args = mock_request.call_args
    assert call_args[0][0] == "/search"
    payload = call_args[0][1]
    assert payload["query"] == "who is messi"
    assert payload["max_results"] == 3
    assert payload["topic"] == "general"
    assert "time_range" not in payload


@patch("tools.builtin.web_search.tool.tavily_request", new_callable=AsyncMock)
async def test_invoke_includes_time_range_when_set(mock_request):
    mock_request.return_value = {"results": []}

    tool = WebSearch()
    args = WebSearchInput(query="latest news", time_range="day")
    await tool.invoke(args, ToolContext())

    payload = mock_request.call_args[0][1]
    assert payload["time_range"] == "day"


@patch("tools.builtin.web_search.tool.tavily_request", new_callable=AsyncMock)
async def test_render_result_with_results(mock_request):
    response = {
        "results": [
            {
                "title": "Messi Bio",
                "url": "https://example.com/messi",
                "content": "Lionel Messi is a footballer.",
            },
            {
                "title": "Messi Stats",
                "url": "https://example.com/stats",
                "content": "800+ goals.",
            },
        ],
    }

    tool = WebSearch()
    rendered = tool.render_result_for_assistant(response)
    assert "[1] Messi Bio" in rendered
    assert "https://example.com/messi" in rendered
    assert "[2] Messi Stats" in rendered
    assert "800+ goals" in rendered


def test_render_result_no_results():
    tool = WebSearch()
    rendered = tool.render_result_for_assistant({"results": []})
    assert "No results found" in rendered


def test_render_result_with_answer():
    tool = WebSearch()
    rendered = tool.render_result_for_assistant(
        {"results": [], "answer": "Messi is a footballer."}
    )
    assert "Messi is a footballer" in rendered
    assert "**Answer:**" in rendered


@patch("tools.builtin.web_search.tool.tavily_request", new_callable=AsyncMock)
async def test_invoke_propagates_tavily_error(mock_request):
    import pytest

    from tools.builtin._tavily.client import TavilyError

    mock_request.side_effect = TavilyError("rate limited")

    tool = WebSearch()
    args = WebSearchInput(query="test")
    with pytest.raises(TavilyError, match="rate limited"):
        await tool.invoke(args, ToolContext())
