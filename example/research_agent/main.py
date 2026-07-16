"""A research agent, served in the browser.

Web search plus read-only file access — no writing, no shell. Run it with:

    uv run main.py        # → http://localhost:8000

Set your API key in the environment (or a .env file in this directory) first —
see .env.example.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from minimal_agent import LLM, Agent, App
from minimal_agent.llm import ReasoningConfig
from minimal_agent.tools.builtin import (
    Glob,
    Grep,
    ReadFile,
    WebExtract,
    WebSearch,
)

load_dotenv()

workspace = Path.cwd()

# The behavior prompt shapes the agent's identity — here, a read-only researcher.
# Resolved relative to this file so it's found no matter where you run from.
behavior = Path(__file__).parent / "behavior.md"

# Reasoning ("thinking") is opt-in and provider-specific: you declare how it's
# requested and where the trace comes back. This shape is for OpenRouter, which
# returns the trace on the `reasoning` field. Delete this and drop
# `reasoning_config` below if your model or backend doesn't reason.
reasoning = ReasoningConfig(response_field="reasoning")

llm = LLM(
    model=os.environ.get("LLM_MODEL", "openai/gpt-4o-mini"),
    backend=os.environ.get("LLM_BACKEND", "openrouter"),
    api_key=os.environ["OPENROUTER_API_KEY"],
    reasoning_config=reasoning,
)

agent = Agent(
    llm=llm,
    tools=[
        ReadFile(workspace_root=workspace, read_timestamps={}),
        Grep(workspace_root=workspace),
        Glob(workspace_root=workspace),
        WebSearch(),
        WebExtract(),
    ],
    prompt=behavior,
    workspace_root=workspace,
)

app = App(agents=agent)

if __name__ == "__main__":
    app.serve()
