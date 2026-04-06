"""Tests for `LLMTool.from_model`.

Pins the contract between our neutral Tool and the OpenAI SDK's
`pydantic_function_tool` helper — specifically that the strict schema
properties and the description-unwrapping survive SDK upgrades.
"""

from pydantic import BaseModel, Field

from llm.types import LLMTool


class GetWeatherArgs(BaseModel):
    """Look up the current weather for a city."""

    city: str = Field(description="City name, e.g. 'San Francisco'")
    units: str = Field(default="F", description="Temperature units")


class NoDocstring(BaseModel):
    x: int


class TestToolFromModel:
    def test_name_defaults_to_class_name(self) -> None:
        tool = LLMTool.from_model(GetWeatherArgs)
        assert tool.name == "GetWeatherArgs"

    def test_explicit_name_overrides_class_name(self) -> None:
        tool = LLMTool.from_model(GetWeatherArgs, name="get_weather")
        assert tool.name == "get_weather"

    def test_description_defaults_to_docstring(self) -> None:
        tool = LLMTool.from_model(GetWeatherArgs)
        assert "weather" in tool.description.lower()

    def test_explicit_description_overrides_docstring(self) -> None:
        tool = LLMTool.from_model(GetWeatherArgs, description="custom desc")
        assert tool.description == "custom desc"

    def test_no_docstring_yields_empty_description(self) -> None:
        tool = LLMTool.from_model(NoDocstring)
        assert tool.description == ""

    def test_strict_schema_has_additional_properties_false(self) -> None:
        """Strict function-calling schemas require additionalProperties=false."""
        tool = LLMTool.from_model(GetWeatherArgs)
        assert tool.parameters.get("additionalProperties") is False

    def test_strict_schema_marks_all_fields_required(self) -> None:
        """Strict schemas put every field in `required`, including those with
        defaults — structured outputs rely on this to avoid missing keys."""
        tool = LLMTool.from_model(GetWeatherArgs)
        assert set(tool.parameters["required"]) == {"city", "units"}

    def test_parameters_has_no_leaked_description(self) -> None:
        """The SDK stashes the docstring inside parameters.description; we
        strip it so `parameters` is a clean JSON Schema and the description
        lives only on the Tool."""
        tool = LLMTool.from_model(GetWeatherArgs)
        assert "description" not in tool.parameters

    def test_parameters_is_object_schema(self) -> None:
        tool = LLMTool.from_model(GetWeatherArgs)
        assert tool.parameters["type"] == "object"
        assert "city" in tool.parameters["properties"]
        assert "units" in tool.parameters["properties"]
