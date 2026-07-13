"""Built-in tools — the batteries-included tool suite.

Each tool lives in its own sub-package (`tools.builtin.read_file`) alongside
its input schema; this module aggregates them so callers import by name
rather than by layout:

    from minimal_agent.tools.builtin import ReadFile, RunShell

`_filesystem` and `_tavily` are shared helpers, not tools — not exported.
"""

from .edit_file import EditFile, EditFileInput
from .glob import Glob, GlobInput
from .grep import Grep, GrepInput
from .read_file import ReadFile, ReadFileInput
from .run_shell import RunShell, RunShellInput
from .skill import SkillInput, SkillOutput, SkillTool
from .spawn_agents import SpawnAgents, SpawnAgentsInput, SubAgentSpec
from .web_extract import WebExtract, WebExtractInput
from .web_search import WebSearch, WebSearchInput
from .write_file import WriteFile, WriteFileInput

__all__ = [
    "EditFile",
    "EditFileInput",
    "Glob",
    "GlobInput",
    "Grep",
    "GrepInput",
    "ReadFile",
    "ReadFileInput",
    "RunShell",
    "RunShellInput",
    "SkillInput",
    "SkillOutput",
    "SkillTool",
    "SpawnAgents",
    "SpawnAgentsInput",
    "SubAgentSpec",
    "WebExtract",
    "WebExtractInput",
    "WebSearch",
    "WebSearchInput",
    "WriteFile",
    "WriteFileInput",
]
