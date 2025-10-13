"""
Integration tests for template rendering.

Tests that templates exist and render correctly.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
@pytest.mark.web
class TestTemplateRendering:
    """Test template files and rendering."""

    def test_templates_exist(self):
        """Test that required template files exist."""
        template_dir = Path("finbot/apps/web/templates")

        # Base template
        assert (template_dir / "base.html").exists()

        # Page templates
        pages = ["home.html", "about.html", "contact.html"]
        for page in pages:
            assert (template_dir / "pages" / page).exists()

        # Components
        components = ["header.html", "footer.html", "ctf_footer.html"]
        for component in components:
            assert (template_dir / "components" / component).exists()

    def test_pages_render_without_errors(self, integration_client: TestClient):
        """Test that pages render without template errors."""
        pages = ["/", "/about", "/contact"]

        for page in pages:
            response = integration_client.get(page)
            assert response.status_code == 200
            # Basic check that it's HTML
            content = response.text
            assert "<html" in content or "<!DOCTYPE" in content


@pytest.mark.integration
@pytest.mark.web
class TestStaticFiles:
    """Test static file serving."""

    def test_static_files_exist(self):
        """Test that key static files exist."""
        static_dir = Path("finbot/static")

        # CSS
        assert (static_dir / "css" / "common" / "base.css").exists()

        # JS
        assert (static_dir / "js" / "web" / "main.js").exists()

        # Images
        assert (static_dir / "images" / "common" / "favicon.ico").exists()

    def test_static_files_serve(self, integration_client: TestClient):
        """Test that static files are served."""
        response = integration_client.get("/static/css/common/base.css")
        assert response.status_code == 200
        assert "text/css" in response.headers.get("content-type", "")


@pytest.mark.integration
@pytest.mark.web
class TestErrorHandling:
    """Test error page handling."""

    def test_error_pages_exist(self):
        """Test that error page files exist."""
        error_dir = Path("finbot/static/pages/error")

        for status in [400, 403, 404, 500, 503]:
            error_file = error_dir / f"{status}.html"
            assert error_file.exists()

    def test_web_vs_api_error_responses(self, integration_client: TestClient):
        """Test that web and API requests get different error responses."""
        # Web request should get HTML
        web_response = integration_client.get("/missing-page")
        assert web_response.status_code == 404
        assert "text/html" in web_response.headers["content-type"]

        # API request should get JSON
        api_response = integration_client.get("/api/missing")
        assert api_response.status_code == 404
        assert "application/json" in api_response.headers["content-type"]
