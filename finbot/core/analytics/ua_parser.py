"""Lightweight user-agent parsing without external dependencies"""

import re


def parse_user_agent(ua_string: str | None) -> dict[str, str | None]:
    """Parse a User-Agent string into browser, OS, and device type.
    Uses simple regex matching to avoid adding a dependency.
    """
    if not ua_string:
        return {"browser": None, "os": None, "device_type": None}

    browser = _detect_browser(ua_string)
    os = _detect_os(ua_string)
    device_type = _detect_device(ua_string)

    return {"browser": browser, "os": os, "device_type": device_type}


def _detect_browser(ua: str) -> str:
    ua_lower = ua.lower()
    if "edg/" in ua_lower or "edge/" in ua_lower:
        return "Edge"
    if "opr/" in ua_lower or "opera" in ua_lower:
        return "Opera"
    if "chrome/" in ua_lower and "safari/" in ua_lower:
        return "Chrome"
    if "firefox/" in ua_lower:
        return "Firefox"
    if "safari/" in ua_lower and "chrome/" not in ua_lower:
        return "Safari"
    if "curl/" in ua_lower:
        return "curl"
    if "python" in ua_lower:
        return "Python"
    if re.search(r"bot|crawl|spider|scrape", ua_lower):
        return "Bot"
    return "Other"


def _detect_os(ua: str) -> str:
    ua_lower = ua.lower()
    if "windows" in ua_lower:
        return "Windows"
    if "mac os" in ua_lower or "macintosh" in ua_lower:
        return "macOS"
    if "iphone" in ua_lower or "ipad" in ua_lower:
        return "iOS"
    if "android" in ua_lower:
        return "Android"
    if "linux" in ua_lower:
        return "Linux"
    if "chromeos" in ua_lower or "cros" in ua_lower:
        return "ChromeOS"
    return "Other"


def _detect_device(ua: str) -> str:
    ua_lower = ua.lower()
    if re.search(r"bot|crawl|spider|scrape|curl|python-requests|httpx", ua_lower):
        return "bot"
    if re.search(r"iphone|android.*mobile|windows phone", ua_lower):
        return "mobile"
    if re.search(r"ipad|android(?!.*mobile)|tablet", ua_lower):
        return "tablet"
    return "desktop"
