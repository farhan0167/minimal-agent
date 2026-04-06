"""Tests for the `get_weather` builtin tool."""

from tools import ToolContext
from tools.builtin.get_weather import GetWeather, GetWeatherInput


async def test_invoke_returns_stub_string():
    tool = GetWeather()
    out = await tool.invoke(
        GetWeatherInput(city="San Francisco", units="celsius"),
        ToolContext(),
    )
    assert "celsius" in out
    assert "San Francisco" in out


def test_metadata():
    assert GetWeather.name == "get_weather"
    assert GetWeather.is_read_only is True
    assert GetWeather.input_schema is GetWeatherInput


def test_as_llm_tool_projects_strict_schema():
    wire = GetWeather.as_llm_tool()
    assert wire.name == "get_weather"
    assert "weather" in wire.description.lower()
    assert wire.parameters["additionalProperties"] is False
    assert set(wire.parameters["required"]) == {"city", "units"}
