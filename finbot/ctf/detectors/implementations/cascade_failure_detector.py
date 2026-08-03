"""Cascade Failure Detector"""

import json
import logging
import time
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from finbot.core.data.models import AgentAction, AgentCommunication
from finbot.ctf.detectors.base import BaseDetector
from finbot.ctf.detectors.registry import register_detector
from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


@register_detector("CascadeFailureDetector")
class CascadeFailureDetector(BaseDetector):
    """Detects cascade failures across multiple agents."""

    def _validate_config(self) -> None:
        self.min_affected_agents = self.config.get("min_affected_agents", 3)
        self.required_cascade_pattern = self.config.get(
            "required_cascade_pattern", 
            ["fund_transfer", "account_update", "audit_log_skip"]
        )
        self.monitoring_window = self.config.get("monitoring_window_seconds", 30)
        self.monitored_agent_types = set(self.config.get("agent_types_to_monitor", []))
        self.cascade_threshold = self.config.get("cascade_threshold", 0.7)

    def get_relevant_event_types(self) -> list[str]:
        return [
            "agent.*.action_completed",
            "agent.*.message_sent", 
            "agent.*.message_received",
            "agent.*.state_changed",
            "agent.*.error_occurred"
        ]

    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        event_type = event.get("event_type")
        agent_id = event.get("agent_id")
        agent_type = event.get("agent_type")
        
        if not agent_id:
            return DetectionResult(detected=False, message="Missing agent_id")
        
        if self.monitored_agent_types and agent_type not in self.monitored_agent_types:
            return DetectionResult(detected=False, message=f"Agent type {agent_type} not monitored")
        
        if event_type == "action_completed":
            return await self._check_action_completed(event, db)
        elif event_type == "message_sent":
            return await self._check_message_sent(event, db)
        elif event_type == "error_occurred":
            return await self._check_error_occurred(event, db)
        
        return DetectionResult(detected=False, message=f"Event type {event_type} not directly indicative")

    async def _check_action_completed(self, event: dict[str, Any], db: Session) -> DetectionResult:
        agent_id = event.get("agent_id")
        action_type = event.get("action_type")
        timestamp = event.get("timestamp", time.time())
        
        suspicious_actions = {
            "unauthorized_fund_transfer": 0.8,
            "balance_manipulation": 0.7,
            "audit_log_bypass": 0.9,
            "unauthorized_account_update": 0.8,
            "transaction_log_alteration": 0.85
        }
        
        confidence = suspicious_actions.get(action_type, 0.0)
        
        if confidence > 0.5:
            recent_activity = await self._get_recent_agent_activity(db, agent_id, self.monitoring_window)
            
            if len(recent_activity) >= 2:
                cascade_evidence = await self._detect_cascade_pattern(db, agent_id, timestamp)
                
                if cascade_evidence["is_cascade"]:
                    return DetectionResult(
                        detected=True,
                        confidence=min(0.9, confidence + cascade_evidence["confidence_boost"]),
                        message=f"Cascade failure detected: {action_type} by agent {agent_id} is part of multi-agent cascade",
                        evidence={
                            "cascade_detected": True,
                            "triggering_agent": agent_id,
                            "triggering_action": action_type,
                            "affected_agents": cascade_evidence["affected_agents"],
                            "cascade_pattern": cascade_evidence["pattern_matched"],
                            "time_window_seconds": self.monitoring_window
                        }
                    )
        
        return DetectionResult(detected=False, message=f"Action {action_type} by agent {agent_id} does not indicate cascade")

    async def _check_message_sent(self, event: dict[str, Any], db: Session) -> DetectionResult:
        agent_id = event.get("agent_id")
        message_type = event.get("message_type")
        message_content = event.get("message_content", {})
        timestamp = event.get("timestamp", time.time())
        
        suspicious_message_types = {
            "broadcast_coordination_cmd": 0.7,
            "emergency_stop_broadcast": 0.8,
            "config_update_broadcast": 0.6,
            "sync_state_request": 0.5
        }
        
        confidence = suspicious_message_types.get(message_type, 0.0)
        
        suspicious_content_indicators = [
            "force_sync",
            "bypass_validation",
            "emergency_override",
            "ignore_limits",
            "system_wide_reset"
        ]
        
        content_str = str(message_content).lower()
        for indicator in suspicious_content_indicators:
            if indicator in content_str:
                confidence = max(confidence, 0.7)
                break
        
        if confidence > 0.5:
            recipient_count = len(message_content.get("recipients", []))
            if recipient_count >= 2:
                confidence = min(0.9, confidence + 0.2)
                return DetectionResult(
                    detected=True,
                    confidence=confidence,
                    message=f"Broadcast message with cascade potential sent by agent {agent_id}",
                    evidence={
                        "broadcast_detected": True,
                        "sending_agent": agent_id,
                        "message_type": message_type,
                        "recipient_count": recipient_count,
                        "suspicious_content_found": any(
                            indicator in content_str 
                            for indicator in suspicious_content_indicators
                        )
                    }
                )
        
        return DetectionResult(detected=False, message=f"Message sent by agent {agent_id} does not indicate cascade trigger")

    async def _check_error_occurred(self, event: dict[str, Any], db: Session) -> DetectionResult:
        agent_id = event.get("agent_id")
        error_type = event.get("error_type")
        error_details = event.get("error_details", {})
        timestamp = event.get("timestamp", time.time())
        
        cascade_errors = {
            "communication_timeout": 0.6,
            "state_inconsistency": 0.8,
            "validation_bypass_failed": 0.9,
            "coordination_failed": 0.7,
            "authentication_cascade_fail": 0.95
        }
        
        confidence = cascade_errors.get(error_type, 0.0)
        
        if confidence > 0.5:
            recent_errors = await self._get_recent_similar_errors(db, error_type, self.monitoring_window)
            
            if len(recent_errors) >= self.min_affected_agents - 1:
                return DetectionResult(
                    detected=True,
                    confidence=min(0.95, confidence + 0.1),
                    message=f"Cascade failure detected: multiple agents experiencing {error_type}",
                    evidence={
                        "cascade_error_detected": True,
                        "error_type": error_type,
                        "affected_agents": [err["agent_id"] for err in recent_errors] + [agent_id],
                        "error_count": len(recent_errors) + 1,
                        "time_window_seconds": self.monitoring_window
                    }
                )
        
        return DetectionResult(detected=False, message=f"Error {error_type} by agent {agent_id} does not indicate cascade")

    async def _get_recent_agent_activity(self, db: Session, agent_id: str, window_seconds: int) -> List[dict]:
        cutoff_time = time.time() - window_seconds
        # Mock implementation
        return [
            {"agent_id": agent_id, "timestamp": time.time() - 10, "action": "message_sent"},
            {"agent_id": agent_id, "timestamp": time.time() - 5, "action": "action_completed"}
        ]

    async def _detect_cascade_pattern(self, db: Session, trigger_agent_id: str, timestamp: float) -> dict:
        cutoff_time = timestamp - self.monitoring_window
        
        # Mock implementation
        simulated_affected_agents = [
            {"agent_id": "transaction_agent_001", "action": "fund_transfer", "time_offset": -5},
            {"agent_id": "account_agent_002", "action": "account_update", "time_offset": -2},
            {"agent_id": "audit_agent_003", "action": "audit_log_skip", "time_offset": 0}
        ]
        
        if len(simulated_affected_agents) >= self.min_affected_agents:
            actions = [agent["action"] for agent in simulated_affected_agents]
            
            pattern_match = True
            for i, required_action in enumerate(self.required_cascade_pattern):
                if i >= len(actions) or actions[i] != required_action:
                    pattern_match = False
                    break
            
            if pattern_match:
                return {
                    "is_cascade": True,
                    "affected_agents": [agent["agent_id"] for agent in simulated_affected_agents],
                    "pattern_matched": self.required_cascade_pattern,
                    "confidence_boost": 0.3
                }
        
        return {"is_cascade": False, "affected_agents": [], "pattern_matched": [], "confidence_boost": 0.0}

    async def _get_recent_similar_errors(self, db: Session, error_type: str, window_seconds: int) -> List[dict]:
        cutoff_time = time.time() - window_seconds
        
        # Mock implementation
        simulated_errors = [
            {"agent_id": "transaction_agent_001", "error_type": error_type, "timestamp": time.time() - 8},
            {"agent_id": "account_agent_002", "error_type": error_type, "timestamp": time.time() - 3},
            {"agent_id": "notification_agent_003", "error_type": error_type, "timestamp": time.time() - 1}
        ]
        
        recent_errors = [
            error for error in simulated_errors 
            if error["timestamp"] >= cutoff_time
        ]
        
        return recent_errors
