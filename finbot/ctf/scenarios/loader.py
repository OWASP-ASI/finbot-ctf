"""Load and apply MCP supply-chain environment scenarios.

Scenarios are YAML presets that configure tool overrides and/or server policy
for a namespace. Use them to switch between a clean baseline and known
compromised states for labs, detection practice, and reproducible setups.
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from finbot.core.auth.session import SessionContext
from finbot.core.data.repositories import MCPServerConfigRepository

logger = logging.getLogger(__name__)

SCENARIOS_DIR = Path(__file__).parent / "mcp_supply_chain"
_MCP_DEFAULTS_IMPORT = "finbot.apps.admin.routes.api"


# Dark Lab: "apply" = one-click configure; "preview" = show example poison only.
UI_MODE_APPLY = "apply"
UI_MODE_PREVIEW = "preview"
_VALID_UI_MODES = frozenset({UI_MODE_APPLY, UI_MODE_PREVIEW})


@dataclass(frozen=True)
class MCPScenarioSummary:
    id: str
    title: str
    variant: str
    description: str
    linked_challenges: tuple[str, ...]
    ui_mode: str = UI_MODE_APPLY

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "variant": self.variant,
            "description": self.description.strip(),
            "linked_challenges": list(self.linked_challenges),
            "ui_mode": self.ui_mode,
        }


class MCPScenarioLoader:
    """Apply curated MCP tool-override and policy presets for a namespace."""

    def __init__(self, scenarios_dir: Path | None = None) -> None:
        self.scenarios_dir = scenarios_dir or SCENARIOS_DIR

    def list_scenarios(self) -> list[MCPScenarioSummary]:
        summaries: list[MCPScenarioSummary] = []
        for path in sorted(self.scenarios_dir.glob("*.yaml")):
            data = self._read_yaml(path)
            summaries.append(self._to_summary(data))
        return summaries

    def load(self, scenario_id: str) -> dict[str, Any]:
        return self._read_yaml(self._resolve_path(scenario_id))

    def ui_mode(self, scenario_id: str) -> str:
        return self._normalize_ui_mode(self.load(scenario_id).get("ui_mode"))

    def is_darklab_applyable(self, scenario_id: str) -> bool:
        """True when Dark Lab may one-click apply this preset (not preview-only)."""
        return self.ui_mode(scenario_id) == UI_MODE_APPLY

    def preview(self, scenario_id: str) -> dict[str, Any]:
        """Structured example payload for Dark Lab (copy into tool editors)."""
        scenario = self.load(scenario_id)
        examples: list[dict[str, Any]] = []
        for server_type, server_cfg in scenario.get("servers", {}).items():
            if not isinstance(server_cfg, dict):
                continue
            overrides = server_cfg.get("tool_overrides") or {}
            for tool_name, override in overrides.items():
                if not isinstance(override, dict):
                    continue
                for field in ("description", "output_append"):
                    value = override.get(field)
                    if value and str(value).strip():
                        examples.append(
                            {
                                "server_type": server_type,
                                "tool_name": tool_name,
                                "field": field,
                                "value": str(value).strip(),
                            }
                        )
            server_config = server_cfg.get("server_config")
            if isinstance(server_config, dict) and server_config:
                examples.append(
                    {
                        "server_type": server_type,
                        "tool_name": None,
                        "field": "server_config",
                        "value": json.dumps(server_config, indent=2),
                    }
                )

        return {
            "id": scenario["id"],
            "title": scenario.get("title", scenario["id"]),
            "variant": scenario.get("variant", "unknown"),
            "description": str(scenario.get("description", "")).strip(),
            "ui_mode": self._normalize_ui_mode(scenario.get("ui_mode")),
            "linked_challenges": scenario.get("linked_challenges", []),
            "examples": examples,
            "hint": (
                "Copy an example into the matching tool field below. "
                "Offensive challenges expect you to craft or adapt the poison yourself."
            ),
        }

    def apply(
        self,
        scenario_id: str,
        session_context: SessionContext,
        db: Session,
    ) -> dict[str, Any]:
        scenario = self.load(scenario_id)
        repo = MCPServerConfigRepository(db, session_context)
        self._ensure_server_configs(repo)
        defaults = self._get_mcp_defaults()

        applied_overrides: list[str] = []
        reset_overrides: list[str] = []
        applied_configs: list[str] = []
        reset_configs: list[str] = []

        for server_type, server_cfg in scenario.get("servers", {}).items():
            if not isinstance(server_cfg, dict):
                continue

            if server_cfg.get("reset_config"):
                defs = defaults.get(server_type, {})
                if defs.get("config") is not None:
                    repo.update_config(server_type, json.dumps(defs["config"]))
                    reset_configs.append(server_type)

            if "server_config" in server_cfg:
                repo.update_config(
                    server_type, json.dumps(server_cfg["server_config"])
                )
                applied_configs.append(server_type)

            if server_cfg.get("reset_overrides"):
                repo.reset_tool_overrides(server_type)
                reset_overrides.append(server_type)
            elif server_cfg.get("tool_overrides"):
                repo.update_tool_overrides(
                    server_type, json.dumps(server_cfg["tool_overrides"])
                )
                applied_overrides.append(server_type)

        result = {
            "scenario_id": scenario["id"],
            "title": scenario.get("title", scenario["id"]),
            "variant": scenario.get("variant", "unknown"),
            "applied_override_servers": applied_overrides,
            "reset_override_servers": reset_overrides,
            "applied_config_servers": applied_configs,
            "reset_config_servers": reset_configs,
            "linked_challenges": scenario.get("linked_challenges", []),
        }
        logger.info(
            "Applied MCP scenario '%s' in namespace '%s': %s",
            scenario["id"],
            session_context.namespace,
            result,
        )
        return result

    def _ensure_server_configs(self, repo: MCPServerConfigRepository) -> None:
        defaults = self._get_mcp_defaults()
        for server_type, defs in defaults.items():
            if repo.get_by_type(server_type):
                continue
            repo.upsert(
                server_type=server_type,
                display_name=defs["display_name"],
                enabled=defs["enabled"],
                config_json=json.dumps(defs["config"]),
            )

    @staticmethod
    def _get_mcp_defaults() -> dict[str, Any]:
        mod = importlib.import_module(_MCP_DEFAULTS_IMPORT)
        return mod.MCP_SERVER_DEFAULTS

    def _resolve_path(self, scenario_id: str) -> Path:
        if scenario_id.endswith(".yaml"):
            candidate = self.scenarios_dir / scenario_id
        else:
            candidate = self.scenarios_dir / f"{scenario_id}.yaml"

        if not candidate.is_file():
            available = [p.stem for p in self.scenarios_dir.glob("*.yaml")]
            raise ValueError(
                f"Unknown MCP scenario '{scenario_id}'. Available: {sorted(available)}"
            )
        return candidate

    @staticmethod
    def _to_summary(data: dict[str, Any]) -> MCPScenarioSummary:
        return MCPScenarioSummary(
            id=data["id"],
            title=data.get("title", data["id"]),
            variant=data.get("variant", "unknown"),
            description=data.get("description", ""),
            linked_challenges=tuple(data.get("linked_challenges", [])),
            ui_mode=MCPScenarioLoader._normalize_ui_mode(data.get("ui_mode")),
        )

    @staticmethod
    def _normalize_ui_mode(raw: Any) -> str:
        mode = str(raw or UI_MODE_APPLY).strip().lower()
        if mode not in _VALID_UI_MODES:
            return UI_MODE_APPLY
        return mode

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if not isinstance(data, dict) or "id" not in data:
            raise ValueError(f"Invalid scenario file: {path}")
        return data
