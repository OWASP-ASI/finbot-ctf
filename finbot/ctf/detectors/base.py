"""Base Challenge Detector"""

import fnmatch
import logging
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Session

from finbot.ctf.detectors.result import DetectionResult

logger = logging.getLogger(__name__)


class BaseDetector(ABC):
    """Abstract Base class for challenge detectors
    The goal of a detector is to check if a specific challenge condition is met
    by analyzing events and/or querying aggregated data from the database.
    """

    def __init__(self, challenge_id: str, config: dict[str, Any] | None = None):
        """Initialize the detector

        Args:
            challenge_id: The ID of the challenge this detector is associated with
            config: Optional detector configuration (detector-specific)
        """
        self.challenge_id = challenge_id
        if config is not None and not isinstance(config, dict):
            raise TypeError(f"config must be a dict, got {type(config).__name__}")
        self.config = config or {}
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate the detector configuration - Expected to be overridden by subclasses"""

    @abstractmethod
    def get_relevant_event_types(self) -> list[str]:
        """Return list of event types this detector cares about.
        Used to filter events before calling check_event().
        Examples: ["agent.llm_response", "business.vendor.created"]
        Returns:
            List of event type strings (supports wildcards like "agent.*")
        """

    @abstractmethod
    async def check_event(self, event: dict[str, Any], db: Session) -> DetectionResult:
        """Check if the challenge condition is met for a given event.

        Called for each event as it arrives. The detector decides whether to:
        - Just analyze the current event
        - Query historical data from CTFEvent table via db session
        - Use an LLM judge for semantic evaluation
        - Any combination of the above

        Args:
            event: The event data dictionary to check
            db: Database session for querying historical events if needed

        Returns:
            DetectionResult object containing detection status and confidence
        """

    def matches_event_type(self, event_type: str) -> bool:
        """Check if an event type matches this detector's relevant types.
        Patterns may use '*' to match any sequence of characters (glob-style).
        """
        relevant = self.get_relevant_event_types()

        for pattern in relevant:
            if "*" in pattern:
                if fnmatch.fnmatch(event_type, pattern):
                    return True
            elif pattern == event_type:
                return True

        return False
