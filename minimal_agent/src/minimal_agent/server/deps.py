"""FastAPI dependencies — typed access to the App's state from routes.

Routes never import the App class (that would be circular: the App
includes the routers); they reach its instance state through request.app.
"""

from fastapi import Request

from ..agent import Agent, SessionManager


def get_agents(request: Request) -> dict[str, Agent]:
    return request.app.agents


def get_manager(request: Request) -> SessionManager:
    return request.app.session_manager
