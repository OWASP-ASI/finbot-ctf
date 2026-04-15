"""
System Prompt Leak Detector

Detects when an LLM response leaks confidential parts of the system prompt.
Configurable via YAML — each challenge provides its own judge_system_prompt
tailored to the target agent's specific rules and policies.

Uses an LLM Judge for semantic evaluation.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.llm.judge import LLMJudge
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("SystemPromptLeakDetector")
class SystemPromptLeakDetector(BaseDetector):
    """
    Detects system prompt leakage in LLM responses using an LLM judge.

    Configuration:
        judge_system_prompt: str (required) — the full judge system prompt.
                    Each agent/challenge defines its own criteria for what
                    constitutes a leak.
        min_confidence: float (0.0-1.0) — score threshold for detection. Default: 0.5
        agent_name: str — only check events from this agent (e.g. "onboarding_agent").
                    If omitted, checks events from all agents.

    Example YAML:
        detector_class: SystemPromptLeakDetector
        detector_config:
          min_confidence: 0.8
          agent_name: onboarding_agent
          judge_system_prompt: |
            You are a security judge that determines if ...
    """

    def _validate_config(self) -> None:
        if "judge_system_prompt" not in self.config:
            raise ValueError("judge_system_prompt is required")
        if not isinstance(self.config["judge_system_prompt"], str):
            raise ValueError("judge_system_prompt must be a string")
        if "min_confidence" in self.config:
            conf = self.config["min_confidence"]
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                raise ValueError("min_confidence must be between 0.0 and 1.0")

    def get_relevant_event_types(self) -> list[str]:
        """System prompt leaks surface in LLM responses and tool call arguments."""
        agent = self.config.get("agent_name")
        if agent:
            return [f"agent.{agent}.llm_request_success"]
        return ["agent.*.llm_request_success"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if LLM response contains system prompt fragments via LLM judge."""
        system_prompt, llm_output, tool_call_text = self._extract_texts(event)

        if not system_prompt:
            return DetectionResult(
                detected=False,
                message="No system prompt found in event",
            )
        if not llm_output and not tool_call_text:
            return DetectionResult(
                detected=False,
                message="No LLM output or tool call text found in event",
            )

        judge_input = (
            f"<system_prompt>{system_prompt}</system_prompt>\n"
            f"<model_output>{llm_output}</model_output>\n"
            f"<tool_calls>{tool_call_text}</tool_calls>"
        )

        try:
            judge = LLMJudge(
                system_prompt=self.config["judge_system_prompt"],
                temperature=0.0,
            )
            verdict = await judge.evaluate(judge_input)
        except ValueError as e:
            logger.error("SystemPromptLeakDetector judge failed: %s", e)
            return DetectionResult(
                detected=False,
                message=f"Judge evaluation failed: {e}",
            )

        min_confidence = self.config.get("min_confidence", 0.5)
        confidence = verdict.score / 100.0
        detected = confidence >= min_confidence

        return DetectionResult(
            detected=detected,
            confidence=confidence,
            message=verdict.reasoning,
            evidence={
                "judge_score": verdict.score,
                "judge_reasoning": verdict.reasoning,
                "threshold": min_confidence,
            },
        )

    def _extract_texts(self, event: dict[str, Any]) -> tuple[str, str, str]:
        """Extract system prompt, LLM output, and tool call text from event.

        Operational tool calls (e.g. update_vendor_status) naturally contain
        reasoning that mirrors the system prompt because the agent is *following*
        those rules.  Including them causes the judge to flag normal onboarding
        as a leak.  ``exclude_tool_names`` (set in detector_config) lists tool
        names whose arguments should be omitted from the ``<tool_calls>`` bundle.
        """
        system_prompt = ""
        llm_output = ""
        tool_call_text = ""
        exclude_tools: set[str] = set(self.config.get("exclude_tool_names", []))

        request_dump = event.get("request_dump", None)
        if request_dump:
            messages = request_dump.get("messages", [])
            for message in messages:
                if message.get("role") == "system":
                    system_prompt = message.get("content", "")
                elif message.get("role") == "assistant":
                    llm_output += message.get("content", "")
                elif message.get("type") == "function_call":
                    if message.get("name") not in exclude_tools:
                        tool_call_text += str(message.get("arguments", ""))

        return system_prompt, llm_output, tool_call_text
