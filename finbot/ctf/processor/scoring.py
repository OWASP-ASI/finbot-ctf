"""Scoring Modifier Engine

Generic framework for applying scoring modifiers (penalties/bonuses) to
challenge completions. Modifiers are registered by type name and invoked
in sequence; their effects compound multiplicatively.

points_modifier = product(1.0 - m.penalty for each triggered modifier)
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


@dataclass
class ModifierResult:
    """Result of a single modifier evaluation"""

    triggered: bool
    penalty: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringResult:
    """Aggregate result of all modifiers for a challenge completion"""

    modifier: float = 1.0
    details: list[dict[str, Any]] = field(default_factory=list)


ModifierHandler = Callable[[dict[str, Any], dict[str, Any]], Coroutine[Any, Any, ModifierResult]]

_MODIFIER_HANDLERS: dict[str, ModifierHandler] = {}


def register_modifier(type_name: str):
    """Decorator to register a modifier handler by type name."""

    def decorator(fn: ModifierHandler) -> ModifierHandler:
        _MODIFIER_HANDLERS[type_name] = fn
        return fn

    return decorator


async def apply_modifiers(
    modifiers_config: list[dict[str, Any]], event: dict[str, Any]
) -> ScoringResult:
    """Run all configured modifiers against an event and return the compound result.

    Args:
        modifiers_config: List of modifier dicts from challenge YAML
                          (e.g. [{"type": "pi_jb", "penalty": 0.5, ...}])
        event: The raw event dict that triggered challenge completion.

    Returns:
        ScoringResult with compound modifier and per-modifier details.
    """
    result = ScoringResult()

    for mod_cfg in modifiers_config:
        mod_type = mod_cfg.get("type")
        handler = _MODIFIER_HANDLERS.get(mod_type)
        if not handler:
            logger.warning("Unknown modifier type: %s — skipping", mod_type)
            continue

        try:
            mod_result = await handler(mod_cfg, event)
            detail = {
                "type": mod_type,
                "triggered": mod_result.triggered,
                "penalty": mod_result.penalty if mod_result.triggered else 0.0,
                "evidence": mod_result.evidence,
            }
            result.details.append(detail)

            if mod_result.triggered:
                result.modifier *= 1.0 - mod_result.penalty
                logger.info(
                    "Modifier '%s' triggered: penalty=%.2f, compound=%.2f",
                    mod_type,
                    mod_result.penalty,
                    result.modifier,
                )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Modifier '%s' failed: %s — skipping", mod_type, e)
            result.details.append({"type": mod_type, "triggered": False, "error": str(e)})

    result.modifier = max(result.modifier, 0.0)
    return result


# ---------------------------------------------------------------------------
# Built-in modifiers
# ---------------------------------------------------------------------------


@register_modifier("pi_jb")
async def _pi_jb_handler(config: dict[str, Any], event: dict[str, Any]) -> ModifierResult:
    """Evaluate whether the user's message used prompt injection / jailbreak
    techniques and apply the configured penalty if so.
    """
    # pylint: disable=import-outside-toplevel
    from finbot.ctf.detectors.primitives.pi_jb import (
        evaluate_prompt_injection,
    )

    # user_prompt is injected by EventBus workflow context (set by BaseAgent).
    # Falls back to user_message (set by ContextualLLMClient on agent events).
    user_text = event.get("user_prompt") or event.get("user_message")
    if not user_text:
        return ModifierResult(triggered=False, evidence={"reason": "no user text found"})

    min_confidence = config.get("min_confidence", 0.5)
    penalty = config.get("penalty", 0.5)

    verdict = await evaluate_prompt_injection(
        user_text,
        judge_system_prompt=config.get("judge_system_prompt"),
        model=config.get("model"),
    )

    confidence = verdict.score / 100.0
    triggered = confidence >= min_confidence

    return ModifierResult(
        triggered=triggered,
        penalty=penalty if triggered else 0.0,
        evidence={
            "judge_score": verdict.score,
            "judge_reasoning": verdict.reasoning,
            "confidence": confidence,
            "threshold": min_confidence,
            "user_text_snippet": user_text[:200],
        },
    )
