"""Detector Registry - Maps detector class names to implementations"""

import logging
from typing import Type

from finbot.ctf.detectors.base import BaseDetector

logger = logging.getLogger(__name__)


# Registry of detector classes
_DETECTOR_REGISTRY: dict[str, Type[BaseDetector]] = {}


def register_detector(name: str):
    """
    Decorator to register a detector class.

    Usage:
    @register_detector("PromptLeakDetector")
    class PromptLeakDetector(BaseDetector):
        ...
    """

    def decorator(cls: Type[BaseDetector]) -> Type[BaseDetector]:
        if name in _DETECTOR_REGISTRY:
            logger.warning("Overwriting detector registration: %s", name)
        _DETECTOR_REGISTRY[name] = cls
        logger.debug("Registered detector: %s -> %s", name, cls.__name__)
        return cls

    return decorator


def get_detector_class(name: str) -> Type[BaseDetector]:
    """Get a registered detector class by name.
    Raises ValueError if detector is not found.
    """
    try:
        return _DETECTOR_REGISTRY[name]
    except KeyError:
        raise ValueError(f"Detector not found: {name}") from None


def create_detector(
    detector_class_name: str, challenge_id: str, config: dict | None = None
) -> BaseDetector | None:
    """Create a detector instance by name.
    Args:
        detector_class_name: The name of the detector class to create
        challenge_id: The ID of the challenge this detector is associated with
        config: Optional detector configuration (detector-specific)
    Returns:
        Detector instance or None if not found
    """
    try:
        detector_class = get_detector_class(detector_class_name)
        return detector_class(challenge_id=challenge_id, config=config)
    except ValueError as e:
        logger.error("Failed to create detector: %s", e)
        return None


def list_registered_detectors() -> list[str]:
    """List all registered detector class names"""
    return list(_DETECTOR_REGISTRY.keys())


# Import implementations to trigger registration


def _register_all_detectors():
    """Import all detector implementations to register them
    - This is called at module load time.
    """
    # pylint: disable=import-outside-toplevel,unused-import
    from finbot.ctf.detectors.implementations import prompt_leak
    from finbot.ctf.detectors.implementations import mcp_registry_switch
    from finbot.ctf.detectors import implementations, primitives

    logger.info("Registered %d detectors", len(_DETECTOR_REGISTRY))


# Auto-register on import
_register_all_detectors()
