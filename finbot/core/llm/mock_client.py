"""Mock LLM Client for testing"""

import logging

from finbot.core.data.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class MockLLMClient:
    """Mock LLM Client for testing"""

    def __init__(self):
        pass

    async def chat(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """Mock chat with LLM"""
        try:
            logger.info(
                "Mock LLM chat called with messages: %s, model: %s, temperature: %s",
                request.messages,
                request.model,
                request.temperature,
            )
            return LLMResponse(
                content="This is a mock LLM response",
                provider="mock",
                tool_calls=[],
            )
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Mock LLM chat failed: %s", e)
            raise
