"""Agent discovery — scans subdirectories for agent modules."""

import importlib
from pathlib import Path

from agents.base import AgentConfig

_AGENTS_DIR = Path(__file__).parent


def _discover_agent_names() -> list[str]:
    """Return sorted list of agent directory names (those containing agent.py)."""
    return sorted(
        d.name
        for d in _AGENTS_DIR.iterdir()
        if d.is_dir() and (d / "agent.py").exists()
    )


def get_agent_config(agent_type: str) -> AgentConfig:
    """Import and return the AgentConfig for the given agent type."""
    mod = importlib.import_module(f"agents.{agent_type}.agent")
    config: AgentConfig = mod.config
    return config


def list_agents() -> list[dict]:
    """Return metadata for all discovered agents."""
    result = []
    for name in _discover_agent_names():
        config = get_agent_config(name)
        result.append({"name": config.name, "display_name": config.display_name})
    return result
