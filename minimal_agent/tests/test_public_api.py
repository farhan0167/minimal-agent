"""The public import surface — see .claude/specifications/public-api-surface.md.

Two tiers: a curated top level (`minimal_agent`) holding what you need to
write the quickstart, and submodules holding the full surface. These tests
pin both, plus the back-compat guarantee that the pre-existing deep paths
still resolve.
"""

import importlib

import pytest

import minimal_agent
import minimal_agent.audit as audit_mod
import minimal_agent.tools.builtin as builtin_mod


def _exports(module) -> list[str]:
    return list(module.__all__)


class TestTopLevel:
    def test_every_exported_name_resolves(self):
        # __all__ is a promise; anything listed must actually be gettable.
        # App is excluded — it is lazy and needs the [server] extra.
        for name in _exports(minimal_agent):
            if name == "App":
                continue
            assert getattr(minimal_agent, name, None) is not None, name

    @pytest.mark.parametrize(
        "name",
        ["Agent", "LLM", "Settings", "settings", "Backend", "Message", "Role"],
    )
    def test_quickstart_symbols_are_top_level(self, name):
        # The inclusion rule: you cannot write the getting-started example
        # without these. Regressing any one of them re-breaks the README.
        assert hasattr(minimal_agent, name)
        assert name in minimal_agent.__all__

    @pytest.mark.parametrize("name", ["BaseTool", "ToolContext"])
    def test_tool_authoring_symbols_are_top_level(self, name):
        # Writing a custom tool is the headline extension point.
        assert hasattr(minimal_agent, name)
        assert name in minimal_agent.__all__


class TestBuiltinTools:
    def test_every_exported_name_resolves(self):
        for name in _exports(builtin_mod):
            assert getattr(builtin_mod, name, None) is not None, name

    @pytest.mark.parametrize(
        "name",
        [
            "EditFile",
            "Glob",
            "Grep",
            "ReadFile",
            "RunShell",
            "SpawnAgents",
            "SkillTool",
            "WebExtract",
            "WebSearch",
            "WriteFile",
        ],
    )
    def test_tools_importable_by_name_not_layout(self, name):
        # The whole point: `from minimal_agent.tools.builtin import ReadFile`,
        # not `...builtin.read_file import ReadFile`.
        assert name in builtin_mod.__all__

    def test_shared_helpers_are_not_exported(self):
        # _filesystem / _tavily are helpers, not tools.
        assert not any(n.startswith("_") for n in builtin_mod.__all__)


class TestAudit:
    def test_every_exported_name_resolves(self):
        for name in _exports(audit_mod):
            assert getattr(audit_mod, name, None) is not None, name

    @pytest.mark.parametrize(
        "name",
        [
            "read_events",
            "read_call_records",
            "read_run_records",
            "read_agent_meta",
            "CallRecordNotFoundError",
            "ToolExecution",
            "CallView",
        ],
    )
    def test_declares_the_names_the_top_level_never_exported(self, name):
        # These were public-by-naming but absent from the root __all__ — the
        # "accidental half" this spec closed. audit.__all__ is now the
        # declared surface, so they must be in it.
        assert name in audit_mod.__all__


class TestSymbolIdentityAcrossPaths:
    """Re-exports must bind the same object, not a copy.

    A future refactor that forks a symbol into two distinct objects would
    silently break `isinstance` for anyone mixing import styles.
    """

    def test_llm(self):
        import minimal_agent.llm as llm_mod

        assert minimal_agent.LLM is llm_mod.LLM

    def test_config(self):
        import minimal_agent.config as config_mod

        assert minimal_agent.Backend is config_mod.Backend
        assert minimal_agent.Settings is config_mod.Settings
        assert minimal_agent.settings is config_mod.settings

    def test_builtin_tool(self):
        from minimal_agent.tools.builtin.read_file import ReadFile as deep

        assert builtin_mod.ReadFile is deep

    def test_audit(self):
        assert minimal_agent.reconstruct_call is audit_mod.reconstruct_call
        assert minimal_agent.session_runs is audit_mod.session_runs


class TestBackCompat:
    """Every pre-existing import path still resolves. Asserted, not assumed."""

    @pytest.mark.parametrize(
        "module, name",
        [
            ("minimal_agent.llm", "LLM"),
            ("minimal_agent.llm", "Message"),
            ("minimal_agent.llm", "Role"),
            ("minimal_agent.config", "Settings"),
            ("minimal_agent.config", "Backend"),
            ("minimal_agent.tools", "BaseTool"),
            ("minimal_agent.tools", "ToolContext"),
            ("minimal_agent.tools.builtin.read_file", "ReadFile"),
            ("minimal_agent.tools.builtin.run_shell", "RunShell"),
            ("minimal_agent.tools.builtin.spawn_agents", "SpawnAgents"),
        ],
    )
    def test_deep_path_still_works(self, module, name):
        assert hasattr(importlib.import_module(module), name)

    @pytest.mark.parametrize(
        "name",
        [
            "reconstruct_call",
            "session_runs",
            "single_run",
            "run_summaries",
            "find_agent_scope",
            "ReconstructedCall",
            "RunSummary",
            "RunView",
            "SpawnedAgent",
        ],
    )
    def test_audit_names_still_at_top_level(self, name):
        # minimal_agent.audit is now the canonical path, but these nine were
        # already published at the root — they stay for back-compat.
        assert hasattr(minimal_agent, name)


class TestGetWeatherRemoved:
    """The stub example tool is gone from the published package."""

    def test_module_is_deleted(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("minimal_agent.tools.builtin.get_weather")

    def test_not_in_builtin_namespace(self):
        assert "GetWeather" not in builtin_mod.__all__
        assert not hasattr(builtin_mod, "GetWeather")


class TestAppStaysLazy:
    """App must not be imported eagerly — it needs the [server] extra."""

    def test_advertised_but_lazy(self):
        assert "App" in minimal_agent.__all__

    def test_unknown_attribute_still_raises(self):
        # The __getattr__ that makes App lazy must not swallow real typos.
        # (Name held in a variable so ruff sees neither a bare expression
        # statement (B018) nor a constant getattr (B009).)
        missing = "NoSuchSymbol"
        with pytest.raises(AttributeError):
            getattr(minimal_agent, missing)
