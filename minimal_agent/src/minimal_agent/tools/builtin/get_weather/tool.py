"""The `get_weather` tool — a stub that returns a fixed temperature.

Exists to exercise the tool system end-to-end; replace the `invoke` body
with a real weather API call when one is wired in.
"""

from ...base import BaseTool
from ...context import ToolContext
from .schema import GetWeatherInput


class GetWeather(BaseTool[GetWeatherInput, str]):
    name = "get_weather"
    input_schema = GetWeatherInput
    is_read_only = True

    async def invoke(self, args: GetWeatherInput, ctx: ToolContext) -> str:
        # Stub: pretend every city is 20° in the requested units.
        return f"20 {args.units} in {args.city}"
