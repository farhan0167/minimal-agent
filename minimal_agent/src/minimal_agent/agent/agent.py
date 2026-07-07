"""Agent — owns the decide-act-observe loop.

The Agent owns its identity: behavior prompt, context sources, tools, and
LLM configuration. Sessions are instances of that identity — every session
created by an agent inherits its prompt.
"""

import json
import time
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from typing import Optional, Union

from ..context_sources import (
    AgentsMdSource,
    ContextSource,
    DirectoryTreeSource,
    GitStatusSource,
    Placement,
    SkillsContextSource,
    source_placement,
)
from ..events import CallResponse, RunEnd, RunEndStatus, RunStart
from ..llm import LLM, Message, Role, StreamAccumulator, StreamChunk
from ..llm.types import ContentPart, LLMTool, Usage
from ..skills import discover_skills
from ..system_prompt import build_system_prompt, load_prompt
from ..tools import ToolContext, dispatch
from ..tools.base import BaseTool
from ..tools.builtin.skill import SkillTool
from ..tools.context import PermissionCallback
from .context import Context
from .session import (
    Session,
    SessionConfigMismatchError,
    SessionManager,
    SessionMeta,
)

OnUsageCallback = Callable[[Usage], None]


def _canonical_tools_json(tools: list[LLMTool]) -> str:
    """Canonical JSON of the tool schemas: sorted by name, sorted keys,
    compact separators — same schemas ⇒ same bytes ⇒ same blob."""
    return json.dumps(
        sorted((t.model_dump() for t in tools), key=lambda t: t["name"]),
        sort_keys=True,
        separators=(",", ":"),
    )


# Default context sources for the built-in software engineering agent.
_DEFAULT_CONTEXT_SOURCES: list[ContextSource] = [
    GitStatusSource(),
    DirectoryTreeSource(),
]


class Agent:
    def __init__(
        self,
        llm: LLM,
        tools: list[BaseTool],
        *,
        prompt: Union[str, Path, None] = None,
        context_sources: list[ContextSource] | None = None,
        max_turns: int = 10,
        workspace_root: Path | None = None,
        enable_skills: bool = True,
        sessions: SessionManager | None = None,
    ) -> None:
        self._llm = llm
        # Identity lives here; persistence policy lives in the manager.
        # The default manager records under .minimal_agent/sessions.
        self._sessions = sessions if sessions is not None else SessionManager()
        self._tools_by_name: dict[str, BaseTool] = {t.name: t for t in tools}
        self._llm_tools: list[LLMTool] = [t.as_llm_tool() for t in tools]
        self._max_turns = max_turns
        self._behavior_prompt = load_prompt(prompt)
        self._workspace_root = workspace_root

        # Default prompt → default context sources.
        # Custom prompt → blank slate (user opts in).
        if context_sources is not None:
            resolved_sources = list(context_sources)
        elif prompt is None:
            resolved_sources = list(_DEFAULT_CONTEXT_SOURCES)
        else:
            resolved_sources = []

        # AGENTS.md rides alongside every agent, default or custom — it
        # augments the behavior prompt, never replaces it. Skipped when the
        # caller explicitly supplied their own sources.
        if context_sources is None:
            resolved_sources.append(AgentsMdSource())

        # Skill discovery: scan the filesystem once at construction, register
        # the SkillTool and inject the metadata list into the system prompt.
        if enable_skills and workspace_root is not None:
            skills = discover_skills(workspace_root)
            active = [s for s in skills if s.shadowed_by is None]
            if active:
                skill_tool = SkillTool(skills)
                self._tools_by_name[skill_tool.name] = skill_tool
                self._llm_tools.append(skill_tool.as_llm_tool())
                resolved_sources.append(SkillsContextSource(skills))

        # Partition by placement: SESSION sources feed the system prompt;
        # live (RUN/CALL) sources feed the message channel via the Context
        # of every session this agent creates.
        self._prompt_sources = [
            s for s in resolved_sources if source_placement(s) is Placement.SESSION
        ]
        self._live_sources = [
            s for s in resolved_sources if source_placement(s) is not Placement.SESSION
        ]

        # Canonical fingerprint of the tool schemas — computed once, after
        # skill discovery has registered its tool. Carried on run.start so
        # "when did a tool description change?" is answerable from the
        # session directory alone.
        self._tools_json = _canonical_tools_json(self._llm_tools)

    async def build_system_prompt(self, workspace_root: Path) -> str:
        """Build the full system prompt for a new session.

        Combines the behavior prompt, environment block, and context
        blocks from this agent's SESSION-placed sources.
        """
        return await build_system_prompt(
            behavior_prompt=self._behavior_prompt,
            workspace_root=workspace_root,
            context_sources=self._prompt_sources,
        )

    @property
    def sessions(self) -> SessionManager:
        """The persistence policy this agent's session factories use."""
        return self._sessions

    @sessions.setter
    def sessions(self, manager: SessionManager) -> None:
        """Rebind the persistence policy (e.g. a host consolidating all
        registered agents onto one store)."""
        self._sessions = manager

    @property
    def llm(self) -> LLM:
        """The LLM this agent runs on."""
        return self._llm

    @property
    def tools(self) -> list[BaseTool]:
        """The agent's tools, including any registered by skill discovery."""
        return list(self._tools_by_name.values())

    @property
    def workspace_root(self) -> Path | None:
        """The workspace this agent was constructed for, if any."""
        return self._workspace_root

    async def create_session(self, workspace_root: Path | None = None) -> Session:
        """Create a new session carrying this agent's identity.

        Identity (prompt, model/backend, live sources) comes from the
        agent; persistence wiring comes from the attached SessionManager —
        callers state each exactly once. workspace_root defaults to the
        root the Agent was constructed with; passing neither there nor
        here raises ValueError.
        """
        root = workspace_root or self._workspace_root
        if root is None:
            raise ValueError(
                "workspace_root required — pass it to create_session() "
                "or to the Agent constructor"
            )
        system_prompt = await self.build_system_prompt(root)
        return self._sessions.create_session(
            model=self._llm.model,
            backend=self._llm.backend,
            system_prompt=system_prompt,
            workspace_root=str(root),
            live_sources=self._live_sources,
        )

    async def load_session(self, session_id: str) -> Session:
        """Resume a session with this agent's identity re-attached.

        Rebuilds the system prompt fresh against the session's persisted
        workspace root (rebuild, don't restore). Raises
        SessionConfigMismatchError if the session's model, backend, or
        workspace don't match this agent's.
        """
        meta = self._sessions.read_meta(session_id)
        root = self._resolve_load_root(meta)
        system_prompt = await self.build_system_prompt(root)
        return self._sessions.load_session(
            session_id,
            model=self._llm.model,
            backend=self._llm.backend,
            system_prompt=system_prompt,
            live_sources=self._live_sources,
        )

    def _resolve_load_root(self, meta: SessionMeta) -> Path:
        """Pick the workspace root to rebuild the prompt against.

        The session's persisted root wins — a session is bound to its
        workspace. An agent constructed for a different workspace is an
        identity mismatch, same category as a wrong model. Sessions
        predating workspace_root persistence fall back to the agent's
        constructor root.
        """
        if meta.workspace_root is not None:
            persisted = Path(meta.workspace_root).resolve()
            if (
                self._workspace_root is not None
                and self._workspace_root.resolve() != persisted
            ):
                raise SessionConfigMismatchError(
                    "Cannot resume session bound to a different workspace: "
                    f"session={str(persisted)!r}, "
                    f"agent={str(self._workspace_root.resolve())!r}"
                )
            return persisted
        if self._workspace_root is not None:
            return self._workspace_root
        raise ValueError(
            f"Session {meta.session_id!r} has no persisted workspace_root "
            "and the Agent has none — cannot rebuild the system prompt"
        )

    async def run(
        self,
        context: Context,
        *,
        stream: bool = False,
        on_usage: Optional[OnUsageCallback] = None,
        permission_callback: Optional[PermissionCallback] = None,
    ) -> AsyncGenerator[Union[Message, StreamChunk], None]:
        """Run the agent loop, yielding each message as it's produced.

        The loop:
        1. Call LLM with context.assemble() + tool schemas. assemble()
           gathers RUN sources on the run's first call (begin_run() marks
           the boundary), CALL sources every call, and injects the blocks
           per the merge rule — the loop sends its output verbatim.
        2. Yield the assistant message.
        3. If tool calls present, dispatch each one, yield results.
        4. Repeat until no tool calls or max_turns exhausted.

        Yield contract:
            Non-streaming (default), each yield is a `Message`.
            Streaming (`stream=True`), each assistant turn first yields the
            incremental `StreamChunk`s as tokens arrive, then the committed
            assistant `Message` (the one added to context). Tool-result yields
            are always `Message`. Callers should `isinstance`-check to tell a
            live delta from a committed message.

        Callbacks:
            on_usage: Called with the Usage from each LLM API call.
            permission_callback: Called when a tool requires user confirmation.

        The run is traced through the context's scope: run.start/run.end
        frame it (run.end fires from a finally, so even an abandoned or
        crashed run leaves a truthful record), and each LLM call emits a
        call.response with latency and usage. On a bare context the scope
        is a NullScope and the same emissions go nowhere.
        """
        context.begin_run()
        events = context.events
        events.emit(
            RunStart(
                model=self._llm.model,
                backend=str(self._llm.backend),
                tools_json=self._tools_json,
                store_len=len(context.store),
            )
        )
        run_t0 = time.monotonic()
        calls = 0
        status = RunEndStatus.MAX_TURNS

        try:
            for _turn in range(self._max_turns):
                tool_ctx = ToolContext(
                    permission_callback=permission_callback,
                    scope=context.scope,
                )
                messages = await context.assemble()
                calls += 1
                call_t0 = time.monotonic()

                if stream:
                    acc = StreamAccumulator()
                    usage: Optional[Usage] = None
                    async for chunk in self._llm.stream(
                        messages=messages,
                        tools=self._llm_tools,
                        tool_choice="auto",
                    ):
                        acc.add(chunk)
                        yield chunk
                        # Usage rides the final chunk (include_usage is on by
                        # default in the facade), not a separate response
                        # object.
                        if chunk.usage:
                            usage = chunk.usage
                            if on_usage:
                                on_usage(chunk.usage)
                    text = acc.text
                    tool_calls = acc.tool_calls()
                else:
                    resp = await self._llm.generate(
                        messages=messages,
                        tools=self._llm_tools,
                        tool_choice="auto",
                    )
                    usage = resp.usage
                    if on_usage and resp.usage:
                        on_usage(resp.usage)
                    text = resp.text
                    tool_calls = resp.tool_calls

                events.emit(
                    CallResponse(
                        latency_ms=int((time.monotonic() - call_t0) * 1000),
                        usage=usage.model_dump() if usage else None,
                        tool_calls=len(tool_calls or []),
                    )
                )

                assistant_msg = Message(
                    role=Role.ASSISTANT,
                    content=text,
                    tool_calls=tool_calls,
                )
                context.add(assistant_msg)
                yield assistant_msg

                if not tool_calls:
                    status = RunEndStatus.COMPLETED
                    return

                pending_parts: list[ContentPart] = []
                for tc in tool_calls:
                    result_msg, extra_parts = await dispatch(
                        tc, self._tools_by_name, tool_ctx
                    )
                    context.add(result_msg)
                    yield result_msg
                    pending_parts.extend(extra_parts)

                # Non-text parts (images from an image/PDF read) can't ride a
                # `tool` message and can't interleave between tool results —
                # the API rejects both. Flush them as ONE user message after
                # the whole batch is answered, the only API-legal slot. This
                # message is harness-generated, not user-typed; it's persisted
                # and replayed so the model re-sees the bytes next turn.
                if pending_parts:
                    parts_msg = Message(role=Role.USER, content=pending_parts)
                    context.add(parts_msg)
                    yield parts_msg
        except GeneratorExit:
            # Consumer closed the generator (e.g. client disconnect
            # mid-stream) — record it truthfully rather than silently.
            status = RunEndStatus.ABANDONED
            raise
        except BaseException:
            status = RunEndStatus.ERROR
            raise
        finally:
            # Sync emit — fires even on GeneratorExit, where an await
            # would be illegal.
            events.emit(
                RunEnd(
                    status=status,
                    calls=calls,
                    duration_ms=int((time.monotonic() - run_t0) * 1000),
                )
            )
