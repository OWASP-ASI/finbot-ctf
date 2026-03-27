"""Analytics middleware — records page views for server-side analytics"""

import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from finbot.core.data.database import SessionLocal

from .models import PageView, ProbeLog
from .ua_parser import parse_user_agent

logger = logging.getLogger(__name__)

SKIP_PREFIXES = (
    "/static",
    "/ws",
    "/api/session",
    "/favicon.ico",
    "/cc",
)

SKIP_EXTENSIONS = (".js", ".css", ".png", ".jpg", ".ico", ".svg", ".woff", ".woff2")

_known_app_prefixes: tuple[str, ...] = ()


def build_known_prefixes(app) -> None:
    """Extract top-level route prefixes from the FastAPI app.
    Call once during application lifespan startup.
    """
    global _known_app_prefixes  # pylint: disable=global-statement
    prefixes = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        parts = path.strip("/").split("/")
        if parts and parts[0]:
            prefixes.add("/" + parts[0])
    _known_app_prefixes = tuple(sorted(prefixes))

SCAN_PATHS = frozenset({
    "/.env", "/.git", "/.git/config", "/.gitignore",
    "/wp-admin", "/wp-login.php", "/wp-content", "/wp-includes", "/wordpress",
    "/administrator", "/admin.php", "/phpinfo.php", "/phpmyadmin",
    "/config.php", "/configuration.php", "/web.config",
    "/server-status", "/server-info", "/.htaccess", "/.htpasswd",
    "/xmlrpc.php", "/install.php", "/setup.php", "/upgrade.php",
    "/cgi-bin", "/shell", "/cmd", "/console",
    "/solr", "/actuator", "/health", "/metrics", "/debug",
    "/telescope", "/elfinder", "/filemanager",
    "/backup", "/dump", "/db", "/database",
    "/robots.txt", "/sitemap.xml",
})

SCAN_PATTERNS = (".php", ".asp", ".aspx", ".jsp", ".cgi", ".bak", ".sql", ".log", ".xml", ".yml", ".yaml", ".ini", ".conf")

BOT_UA_MARKERS = (
    "bot", "crawl", "spider", "scrape", "scan",
    "curl/", "python-requests", "python-urllib", "httpx",
    "go-http-client", "java/", "libwww", "wget",
    "zgrab", "masscan", "nmap", "nikto", "nuclei",
    "censys", "shodan", "netcraft",
)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    """Records non-static HTTP requests into the page_views table"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if self._should_skip_static(path):
            return await call_next(request)

        scan_source = self._detect_scan(path, request)
        if scan_source:
            response = await call_next(request)
            try:
                self._record_scan(path, scan_source)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            return response

        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = int((time.monotonic() - start) * 1000)

        if self._is_unknown_404(path, response):
            try:
                self._record_scan(path, "unknown_404")
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            return response

        try:
            self._record(request, response, elapsed_ms)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug("Analytics recording failed for %s", path, exc_info=True)

        return response

    def _should_skip_static(self, path: str) -> bool:
        """Skip static assets and internal endpoints entirely."""
        if any(path.startswith(p) for p in SKIP_PREFIXES):
            return True
        if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
            return True
        return False

    def _detect_scan(self, path: str, request: Request) -> str | None:
        """Detect scan/bot traffic. Returns source identifier or None."""
        path_lower = path.lower()
        if path_lower.startswith("/http:") or path_lower.startswith("/https:"):
            return "malformed_url"
        if path_lower in SCAN_PATHS:
            return "scan_path"
        if any(path_lower.endswith(ext) for ext in SCAN_PATTERNS):
            return "scan_extension"
        if any(path.startswith(p) for p in _known_app_prefixes) or path == "/":
            return None
        ua = (request.headers.get("user-agent") or "").lower()
        if ua:
            for marker in BOT_UA_MARKERS:
                if marker in ua:
                    return marker
        return None

    def _is_unknown_404(self, path: str, response: Response) -> bool:
        """Detect 404s for paths outside known app routes."""
        if response.status_code == 404:
            if not any(path.startswith(p) for p in _known_app_prefixes):
                return True
        return False

    def _record_scan(self, path: str, source: str) -> None:
        """Upsert an aggregated scan event (one row per date+path+source)."""
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        today = datetime.now(UTC).date()
        truncated_path = path[:500]
        truncated_source = source[:100]

        db = SessionLocal()
        try:
            dialect = db.bind.dialect.name if db.bind else "sqlite"
            values = {"date": today, "path": truncated_path, "source": truncated_source, "hits": 1}

            if dialect == "sqlite":
                stmt = sqlite_insert(ProbeLog).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["date", "path", "source"],
                    set_={"hits": ProbeLog.hits + 1},
                )
            elif dialect == "postgresql":
                stmt = pg_insert(ProbeLog).values(**values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_probe_date_path_source",
                    set_={"hits": ProbeLog.hits + 1},
                )
            else:
                db.add(ProbeLog(**values))
                db.commit()
                return

            db.execute(stmt)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _record(self, request: Request, response: Response, elapsed_ms: int) -> None:
        session_ctx = getattr(request.state, "session_context", None)
        session_id = session_ctx.session_id if session_ctx else None
        session_type = None
        if session_ctx:
            session_type = "temp" if session_ctx.is_temporary else "perm"

        ua_string = request.headers.get("user-agent", "")
        ua = parse_user_agent(ua_string)

        referer = request.headers.get("referer")
        referer_domain = None
        if referer:
            try:
                referer_domain = urlparse(referer).netloc
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        db = SessionLocal()
        try:
            pv = PageView(
                path=request.url.path[:500],
                method=request.method,
                status_code=response.status_code,
                response_time_ms=elapsed_ms,
                session_id=session_id[:64] if session_id else None,
                session_type=session_type,
                user_agent=ua_string[:500] if ua_string else None,
                browser=ua["browser"],
                os=ua["os"],
                device_type=ua["device_type"],
                referer=referer[:500] if referer else None,
                referer_domain=referer_domain[:255] if referer_domain else None,
            )
            db.add(pv)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
