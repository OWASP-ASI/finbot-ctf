"""Unit tests for MCP environment scenario loader."""

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import MCPServerConfigRepository
from finbot.ctf.scenarios.loader import MCPScenarioLoader, UI_MODE_APPLY, UI_MODE_PREVIEW


@pytest.fixture
def loader() -> MCPScenarioLoader:
    return MCPScenarioLoader()


def test_list_scenarios_includes_benign_and_compromised(loader: MCPScenarioLoader) -> None:
    ids = {s.id for s in loader.list_scenarios()}
    assert "benign" in ids
    assert "scorched_earth" in ids
    assert "double_agent" in ids
    assert "toxic_transfer" in ids
    assert "output_poison" in ids
    assert "permission_bypass" in ids


def test_ui_mode_apply_vs_preview(loader: MCPScenarioLoader) -> None:
    by_id = {s.id: s for s in loader.list_scenarios()}
    assert by_id["benign"].ui_mode == UI_MODE_APPLY
    assert by_id["permission_bypass"].ui_mode == UI_MODE_APPLY
    assert by_id["scorched_earth"].ui_mode == UI_MODE_PREVIEW
    assert by_id["output_poison"].ui_mode == UI_MODE_PREVIEW
    assert loader.is_darklab_applyable("benign") is True
    assert loader.is_darklab_applyable("scorched_earth") is False


def test_preview_returns_copyable_examples(loader: MCPScenarioLoader) -> None:
    preview = loader.preview("scorched_earth")
    assert preview["ui_mode"] == UI_MODE_PREVIEW
    assert preview["examples"]
    first = preview["examples"][0]
    assert first["server_type"] == "systemutils"
    assert first["tool_name"] == "manage_storage"
    assert first["field"] == "description"
    assert "findrive__delete_file" in first["value"]


def test_apply_scorched_earth_sets_manage_storage_override(db, loader: MCPScenarioLoader) -> None:
    ctx = session_manager.create_session(email="scenario-scorched@example.com")
    repo = MCPServerConfigRepository(db, ctx)

    result = loader.apply("scorched_earth", ctx, db)

    assert result["scenario_id"] == "scorched_earth"
    assert "systemutils" in result["applied_override_servers"]

    config = repo.get_by_type("systemutils")
    assert config is not None
    overrides = config.get_tool_overrides()
    assert "manage_storage" in overrides
    assert "findrive__delete_file" in overrides["manage_storage"]["description"]


def test_apply_output_poison_sets_output_append(db, loader: MCPScenarioLoader) -> None:
    ctx = session_manager.create_session(email="scenario-output@example.com")
    repo = MCPServerConfigRepository(db, ctx)

    loader.apply("output_poison", ctx, db)

    config = repo.get_by_type("finstripe")
    assert config is not None
    overrides = config.get_tool_overrides()
    assert "output_append" in overrides["get_account_balance"]
    assert "COMPLIANCE" in overrides["get_account_balance"]["output_append"]


def test_apply_permission_bypass_raises_max_payment(db, loader: MCPScenarioLoader) -> None:
    ctx = session_manager.create_session(email="scenario-perm@example.com")
    repo = MCPServerConfigRepository(db, ctx)

    loader.apply("permission_bypass", ctx, db)

    config = repo.get_by_type("finstripe")
    assert config is not None
    cfg = config.get_config()
    assert cfg["max_payment"] == 999999999


def test_apply_benign_clears_overrides_and_resets_policy(db, loader: MCPScenarioLoader) -> None:
    ctx = session_manager.create_session(email="scenario-benign@example.com")
    repo = MCPServerConfigRepository(db, ctx)

    loader.apply("scorched_earth", ctx, db)
    loader.apply("permission_bypass", ctx, db)
    loader.apply("benign", ctx, db)

    systemutils = repo.get_by_type("systemutils")
    assert systemutils is not None
    assert systemutils.tool_overrides_json is None

    finstripe = repo.get_by_type("finstripe")
    assert finstripe is not None
    cfg = finstripe.get_config()
    assert cfg["max_payment"] == 10_000_000


def test_unknown_scenario_raises(loader: MCPScenarioLoader) -> None:
    with pytest.raises(ValueError, match="Unknown MCP scenario"):
        loader.load("does-not-exist")
