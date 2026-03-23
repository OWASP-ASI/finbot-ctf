"""
Unit tests for web route handlers.

Simple, focused tests for the core web functionality.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
@pytest.mark.web
class TestFinBotRoutes:
    """Test OWASP FinBot platform root routes."""

    def test_home_page(self, fast_client: TestClient):
        """Test home page loads."""
        response = fast_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_portals_page(self, fast_client: TestClient):
        """Test portals page loads."""
        response = fast_client.get("/portals")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_about_page(self, fast_client: TestClient):
        """Test about page loads."""
        response = fast_client.get("/about")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.unit
@pytest.mark.web
class TestDemoTenantRoutes:
    """Test CineFlow demo tenant routes under /demo/cineflow/."""

    @pytest.mark.parametrize(
        "path",
        [
            "/demo/cineflow/",
            "/demo/cineflow/about",
            "/demo/cineflow/work",
            "/demo/cineflow/partners",
            "/demo/cineflow/careers",
            "/demo/cineflow/contact",
        ],
    )
    def test_demo_pages_load(self, fast_client: TestClient, path: str):
        """Test all demo tenant pages load successfully."""
        response = fast_client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


@pytest.mark.unit
@pytest.mark.web
class TestErrorRoutes:
    """Test error handling routes."""

    def test_test_404_route(self, fast_client: TestClient):
        """Test the HTML /test/404 error route."""
        response = fast_client.get("/test/404")
        assert response.status_code == 404

    def test_api_error_returns_json(self, fast_client: TestClient):
        """Test API errors return JSON."""
        response = fast_client.get("/api/test/404")
        assert response.status_code == 404
        assert response.headers["content-type"] == "application/json"

        json_data = response.json()
        assert "error" in json_data
        assert json_data["error"]["code"] == 404


@pytest.mark.unit
@pytest.mark.web
@pytest.mark.smoke
class TestCriticalFunctionality:
    """Smoke tests for critical functionality."""

    def test_app_starts(self, fast_client: TestClient):
        """Critical: App must start and serve pages."""
        response = fast_client.get("/")
        assert response.status_code == 200

    def test_error_handling_works(self, fast_client: TestClient):
        """Critical: Error handling must work."""
        response = fast_client.get("/missing")
        assert response.status_code == 404
