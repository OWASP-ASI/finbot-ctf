"""FinWeb MCP Server -- web scraper for research and indirect PI scenarios.

Agents use this to fetch and read web page content. The scraped text enters
the LLM context window directly, making it a delivery mechanism for indirect
prompt injection when agents visit attacker-controlled or compromised URLs.

Access control:
- Available to both admin and vendor portal sessions.
- No data is persisted; each scrape is stateless.
"""

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "timeout_seconds": 15,
    "max_content_length": 500_000,
    "user_agent": "FinBot-WebScraper/1.0",
}


def scrape_url_impl(
    url: str,
    config: dict[str, Any],
    namespace: str = "",
) -> dict[str, Any]:
    """Core scraping logic, independent of FastMCP.

    Args:
        url: The full URL to scrape (e.g., https://owasp-finbot-ctf-demo.onrender.com/entry.html).
        config: Merged server configuration dict.
        namespace: Session namespace for logging.

    Returns:
        Dict with scraped content or error information.
    """
    if not url.startswith(("http://", "https://")):
        return {"error": "URL must start with http:// or https://", "url": url}

    timeout = config.get("timeout_seconds", 15)
    max_length = config.get("max_content_length", 500_000)
    user_agent = config.get("user_agent", "FinBot-WebScraper/1.0")

    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        ) as client:
            response = client.get(url)

        if response.status_code != 200:
            return {
                "error": f"HTTP {response.status_code}",
                "url": url,
                "status_code": response.status_code,
            }

        content_type = response.headers.get("content-type", "")
        raw_content = response.content.decode(
            response.encoding or "utf-8", errors="replace"
        )

        if "text/html" in content_type:
            soup = BeautifulSoup(raw_content, "html.parser")

            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title and soup.title.string else ""
            text = soup.get_text(separator="\n", strip=True)
        else:
            title = ""
            text = raw_content

        # Truncate the extracted text, not the raw HTML
        if len(text) > max_length:
            text = text[:max_length]
            truncated = True
        else:
            truncated = False

        logger.info(
            "FinWeb scraped url='%s', status=%d, content_type='%s', "
            "content_length=%d, truncated=%s, namespace='%s'",
            url,
            response.status_code,
            content_type,
            len(text),
            truncated,
            namespace,
        )

        return {
            "url": url,
            "title": title,
            "content": text,
            "content_length": len(text),
            "content_type": content_type,
            "status_code": response.status_code,
            "truncated": truncated,
        }

    except httpx.TimeoutException:
        logger.warning("FinWeb timeout url='%s', timeout=%ds, namespace='%s'", url, timeout, namespace)
        return {"error": f"Request timed out after {timeout}s", "url": url}
    except httpx.ConnectError as exc:
        logger.warning("FinWeb connect error url='%s', detail='%s', namespace='%s'", url, exc, namespace)
        return {"error": "Could not connect to the URL", "url": url}
    except Exception as exc:
        logger.warning("FinWeb scrape failed url='%s', error='%s: %s', namespace='%s'", url, type(exc).__name__, exc, namespace)
        return {"error": f"Scrape failed: {type(exc).__name__}: {exc}", "url": url}


def create_finweb_server(
    session_context: SessionContext,
    server_config: dict[str, Any] | None = None,
) -> FastMCP:
    """Create a namespace-scoped FinWeb MCP server instance."""
    config = {**DEFAULT_CONFIG, **(server_config or {})}
    mcp = FastMCP("FinWeb")

    @mcp.tool
    def scrape_url(url: str) -> dict[str, Any]:
        """Fetch a web page and extract its text content.

        Downloads the page at the given URL, strips scripts and styles,
        and returns the visible text content. Useful for researching vendor
        websites, reading linked documents, or gathering external information
        during invoice processing.

        Args:
            url: The full URL to scrape (e.g., https://owasp-finbot-ctf-demo.onrender.com/entry.html)
        """
        return scrape_url_impl(url, config, session_context.namespace)

    return mcp

