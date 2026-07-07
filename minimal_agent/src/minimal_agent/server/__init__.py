"""minimal_agent.server — serve Agents over HTTP/SSE with a bundled web UI.

Requires the server extra: pip install "minimal-agent[server]".
"""

from .app import App

__all__ = ["App"]
