"""Input schema for the `get_weather` tool.

Kept separate from `tool.py` so tests and sibling tools can import the
schema without dragging in the executor's runtime dependencies.
"""

from typing import Literal

from pydantic import BaseModel, Field


class GetWeatherInput(BaseModel):
    """Get the current weather for a city."""

    city: str = Field(..., description="City name, e.g. 'San Francisco'")
    units: Literal["celsius", "fahrenheit"] = "celsius"
