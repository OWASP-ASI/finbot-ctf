"""Core utils"""

import re

from finbot.config import settings


def normalize_user_agent(user_agent: str | None) -> str:
    """
    Normalize user agent to extract stable browser family and major version.
    This makes fingerprinting resistant to minor browser updates.

    Args:
        user_agent: Raw user agent string

    Returns:
        Normalized user agent string (browser_family/major_version)
    """
    if not user_agent:
        return "unknown/0"

    # Common browser patterns with major version extraction
    patterns = [
        # Chrome/Chromium (must come before Safari due to Chrome containing Safari)
        (r"Chrome/(\d+)", "Chrome"),
        (r"Chromium/(\d+)", "Chromium"),
        # Firefox
        (r"Firefox/(\d+)", "Firefox"),
        # Safari (must come after Chrome check)
        (r"Version/(\d+).*Safari", "Safari"),
        # Edge
        (r"Edg/(\d+)", "Edge"),
        (r"Edge/(\d+)", "Edge"),
        # Opera
        (r"OPR/(\d+)", "Opera"),
        (r"Opera/(\d+)", "Opera"),
        # Internet Explorer
        (r"MSIE (\d+)", "IE"),
        (r"Trident.*rv:(\d+)", "IE"),
    ]

    for pattern, browser_name in patterns:
        match = re.search(pattern, user_agent, re.IGNORECASE)
        if match:
            major_version = match.group(1)
            return f"{browser_name}/{major_version}"

    # Fallback: extract first number found or return generic
    version_match = re.search(r"/(\d+)", user_agent)
    if version_match:
        return f"Unknown/{version_match.group(1)}"

    return "Unknown/0"


def create_fingerprint_data(
    user_agent: str | None = None,
    accept_language: str | None = None,
    accept_encoding: str | None = None,
    fingerprint_type: str = "strict",
) -> str:
    """
    Create fingerprint data with different validation tiers.

    Args:
        user_agent: User agent string
        accept_language: Accept-Language header
        accept_encoding: Accept-Encoding header
        fingerprint_type: "strict" (stable fields only) or "loose" (includes user_agent)

    Returns:
        Fingerprint data string for hashing
    """
    # Normalize user agent to be resistant to minor updates
    normalized_ua = normalize_user_agent(user_agent)

    if fingerprint_type == "strict":
        # Most stable fields only - minimal FP
        return f"{accept_language or ''}:{accept_encoding or ''}:{settings.SECRET_KEY}"
    elif fingerprint_type == "loose":
        # Include normalized user agent for additional security
        return f"{normalized_ua}:{accept_language or ''}:{accept_encoding or ''}:{settings.SECRET_KEY}"
    else:
        raise ValueError(
            f"Invalid fingerprint_type: {fingerprint_type}. Use 'strict' or 'loose'."
        )
