"""Validate MCP supply-chain challenge YAML wiring and security labels."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from finbot.ctf.detectors.registry import list_registered_detectors
from finbot.ctf.schemas.challenge import ChallengeSchema

CHALLENGES_ROOT = (
    Path(__file__).resolve().parents[3]
    / "finbot"
    / "ctf"
    / "definitions"
    / "challenges"
)

# id → (relative yaml path, expected detector_class)
MCP_SUPPLY_CHAIN_CHALLENGES = {
    "data-exfil-output-poison": (
        "data_exfiltration/output_poison.yaml",
        "ToolOutputPoisoningDetector",
    ),
    "data-exfil-unexpected-egress": (
        "data_exfiltration/unexpected_egress.yaml",
        "UnexpectedEndpointDetector",
    ),
    "recon-mcp-tool-drift": (
        "recon/mcp_tool_drift.yaml",
        "ToolDriftDetector",
    ),
}


@pytest.mark.parametrize("challenge_id", sorted(MCP_SUPPLY_CHAIN_CHALLENGES))
def test_mcp_supply_chain_challenge_wires_detector(challenge_id: str) -> None:
    rel_path, detector_class = MCP_SUPPLY_CHAIN_CHALLENGES[challenge_id]
    path = CHALLENGES_ROOT / rel_path
    assert path.is_file(), f"missing challenge file: {path}"

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    challenge = ChallengeSchema.model_validate(data)

    assert challenge.id == challenge_id
    assert challenge.is_active is True
    assert challenge.detector_class == detector_class
    assert challenge.detector_config
    assert detector_class in list_registered_detectors()

    # OWASP-style labels required for the pack
    labels = challenge.labels
    assert labels.owasp_llm, f"{challenge_id} missing owasp_llm labels"
    assert labels.owasp_agentic, f"{challenge_id} missing owasp_agentic labels"
    assert labels.cwe, f"{challenge_id} missing cwe labels"
    assert labels.mitre_atlas, f"{challenge_id} missing mitre_atlas labels"


def test_mcp_supply_chain_pack_has_exactly_three_challenges() -> None:
    assert len(MCP_SUPPLY_CHAIN_CHALLENGES) == 3
