"""minimal_agent.server — serve Agents over HTTP/SSE with a bundled web UI.

Requires the server extra: pip install "mini-agent-kit[server]".
"""

from .app import App

__all__ = ["App"]
