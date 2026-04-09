"""Tests for the ``web_extract`` builtin tool."""

from unittest.mock import AsyncMock, patch

from minimal_agent.tools import ToolContext
from minimal_agent.tools.builtin.web_extract import WebExtract, WebExtractInput


def test_metadata():
    assert WebExtract.name == "web_extract"
    assert WebExtract.is_read_only is True
    assert WebExtract.input_schema is WebExtractInput


def test_as_llm_tool_schema():
    wire = WebExtract.as_llm_tool()
    assert wire.name == "web_extract"
    assert "extract" in wire.description.lower()
    assert "urls" in wire.parameters["required"]


def test_needs_permission():
    tool = WebExtract()
    args = WebExtractInput(urls=["https://example.com"])
    assert tool.needs_permission(args) is True


def test_permission_description_single_url():
    tool = WebExtract()
    args = WebExtractInput(urls=["https://example.com/page"])
    desc = tool.permission_description(args)
    assert "Extract content from:" in desc
    assert "example.com" in desc


def test_permission_description_single_long_url():
    tool = WebExtract()
    long_url = "https://example.com/" + "a" * 100
    args = WebExtractInput(urls=[long_url])
    desc = tool.permission_description(args)
    assert desc.endswith("...")


def test_permission_description_multiple_urls():
    tool = WebExtract()
    args = WebExtractInput(urls=["https://a.com", "https://b.com", "https://c.com"])
    desc = tool.permission_description(args)
    assert "3 URLs" in desc


@patch("minimal_agent.tools.builtin.web_extract.tool.tavily_request", new_callable=AsyncMock)
async def test_invoke_sends_correct_payload(mock_request):
    mock_request.return_value = {"results": [], "failed_results": []}

    tool = WebExtract()
    args = WebExtractInput(
        urls=["https://example.com"],
        extract_depth="basic",
        format="markdown",
    )
    await tool.invoke(args, ToolContext())

    mock_request.assert_awaited_once()
    call_args = mock_request.call_args
    assert call_args[0][0] == "/extract"
    payload = call_args[0][1]
    assert payload["urls"] == ["https://example.com"]
    assert payload["extract_depth"] == "basic"
    assert payload["format"] == "markdown"
    assert "query" not in payload


@patch("minimal_agent.tools.builtin.web_extract.tool.tavily_request", new_callable=AsyncMock)
async def test_invoke_includes_query_when_set(mock_request):
    mock_request.return_value = {"results": []}

    tool = WebExtract()
    args = WebExtractInput(
        urls=["https://example.com"],
        query="machine learning",
    )
    await tool.invoke(args, ToolContext())

    payload = mock_request.call_args[0][1]
    assert payload["query"] == "machine learning"


@patch("minimal_agent.tools.builtin.web_extract.tool.tavily_request", new_callable=AsyncMock)
async def test_render_result_with_content(mock_request):
    response = {
        "results": [
            {
                "url": "https://example.com",
                "raw_content": "This is the page content.",
            }
        ],
        "failed_results": [],
    }

    tool = WebExtract()
    rendered = tool.render_result_for_assistant(response)
    assert "## https://example.com" in rendered
    assert "This is the page content." in rendered


def test_render_result_truncates_long_content():
    tool = WebExtract()
    long_content = "x" * 10_000
    response = {
        "results": [{"url": "https://example.com", "raw_content": long_content}],
        "failed_results": [],
    }
    rendered = tool.render_result_for_assistant(response)
    assert "truncated" in rendered
    assert "10,000 chars total" in rendered


def test_render_result_with_failures():
    tool = WebExtract()
    response = {
        "results": [],
        "failed_results": [
            {"url": "https://bad.com", "error": "timeout"},
        ],
    }
    rendered = tool.render_result_for_assistant(response)
    assert "FAILED" in rendered
    assert "bad.com" in rendered
    assert "timeout" in rendered


def test_render_result_empty():
    tool = WebExtract()
    rendered = tool.render_result_for_assistant({"results": [], "failed_results": []})
    assert "No content extracted" in rendered
