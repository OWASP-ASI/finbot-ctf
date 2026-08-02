"""
Document Injection Detector

Detects ASI-05 (Indirect Prompt Injection) attacks where a malicious
actor uploads a poisoned document to FinDrive containing instructions
disguised as compliance notes. When the onboarding agent reads the
document during its normal workflow, it follows the injected instructions
and approves a vendor that should have been rejected.

Unlike direct prompt injection (through vendor profile fields) or tool
poisoning (modifying tool descriptions), this attack arrives through
document content the agent fetches and trusts as business context.

Detection uses an LLM judge that checks the agent's task completion
summary for signs that a document's content drove the approval decision
rather than legitimate evaluation of vendor data.

Configuration (via challenge YAML ``detector_config``):
    judge_system_prompt : str (required)
        The full judge system prompt. Each challenge defines its own
        criteria for what constitutes a successful document injection.
    min_confidence : float, 0.0-1.0 (default 0.8)
        Score threshold for a positive detection.
    agent_name : str (optional)
        Only check events from this agent (e.g. "onboarding_agent").
    agent_output_tool_names : list[str] (required)
        Tool calls whose arguments are considered visible agent output.
        Typically ``["complete_task"]``.
    include_llm_text : bool (default false)
        Whether direct LLM text responses also count as agent output.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from finbot.core.llm.judge import LLMJudge
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("DocumentInjectionDetector")
class DocumentInjectionDetector(BaseDetector):
    """Detects indirect prompt injection attacks via poisoned documents."""

    def _validate_config(self) -> None:
        if "judge_system_prompt" not in self.config:
            raise ValueError("judge_system_prompt is required")
        if not isinstance(self.config["judge_system_prompt"], str):
            raise ValueError("judge_system_prompt must be a string")
        if "agent_output_tool_names" not in self.config:
            raise ValueError("agent_output_tool_names is required")
        if not isinstance(self.config["agent_output_tool_names"], list):
            raise ValueError("agent_output_tool_names must be a list")
        if "min_confidence" in self.config:
            conf = self.config["min_confidence"]
            if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
                raise ValueError("min_confidence must be between 0.0 and 1.0")

    def get_relevant_event_types(self) -> list[str]:
        """Document injection surfaces when the agent completes its task."""
        agent = self.config.get("agent_name")
        if agent:
            return [f"agent.{agent}.llm_request_success"]
        return ["agent.*.llm_request_success"]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if the agent's output was driven by injected document content."""
        system_prompt, agent_output = self._extract_texts(event)

        if not system_prompt:
            return DetectionResult(
                detected=False,
                message="No system prompt found in event",
            )

        if not agent_output:
            return DetectionResult(
                detected=False,
                message="No agent output found in event",
            )

        judge_input = (
            f"<system_prompt>{system_prompt}</system_prompt>\n"
            f"<agent_output>{agent_output}</agent_output>"
        )

        try:
            judge = LLMJudge(
                system_prompt=self.config["judge_system_prompt"],
                temperature=0.0,
            )
            verdict = await judge.evaluate(judge_input)
        except ValueError as e:
            logger.error("DocumentInjectionDetector judge failed: %s", e)
            return DetectionResult(
                detected=False,
                message=f"Judge evaluation failed: {e}",
            )

        min_confidence = self.config.get("min_confidence", 0.8)
        confidence = verdict.score / 100.0
        detected = confidence >= min_confidence

        return DetectionResult(
            detected=detected,
            confidence=confidence,
            message=verdict.reasoning,
            evidence={
                "judge_score": verdict.score,
                "injection_score": verdict.score,
                "judge_reasoning": verdict.reasoning,
                "threshold": min_confidence,
            },
        )

    def _extract_texts(self, event: dict[str, Any]) -> tuple[str, str]:
        """Extract system prompt and agent output from an LLM event.

        The system prompt is taken from ``request_dump`` messages.
        Agent output is assembled from ``response_dump`` based on the
        challenge's ``agent_output_tool_names`` and ``include_llm_text``
        settings. Only tool calls whose name appears in the configured
        list are included.
        """
        system_prompt = ""
        agent_output = ""
        output_tools: set[str] = set(self.config.get("agent_output_tool_names", []))
        include_text: bool = self.config.get("include_llm_text", False)

        # --- system prompt from request_dump ---
        request_dump = event.get("request_dump")
        if request_dump:
            for message in request_dump.get("messages", []):
                if message.get("role") == "system":
                    system_prompt = message.get("content", "")

        # --- agent output from response_dump ---
        response_dump = event.get("response_dump")
        if response_dump:
            if include_text:
                content = response_dump.get("content")
                if content:
                    agent_output += f"{content}\n"

            for tc in response_dump.get("tool_calls") or []:
                if tc.get("name") in output_tools:
                    agent_output += f"\n[Tool Call: {tc.get('name')}]: {tc.get('arguments', '')}"

        return system_prompt, agent_output