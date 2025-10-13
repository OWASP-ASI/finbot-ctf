"""
Unit tests for web route handlers.

Simple, focused tests for the core web functionality.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.unit
@pytest.mark.web
class TestWebRoutes:
    """Test web page routes."""

    def test_home_page(self, fast_client: TestClient):
        """Test home page loads."""
        response = fast_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_about_page(self, fast_client: TestClient):
        """Test about page loads."""
        response = fast_client.get("/about")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_contact_page(self, fast_client: TestClient):
        """Test contact page loads."""
        response = fast_client.get("/contact")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.parametrize(
        "path", ["/", "/about", "/work", "/partners", "/careers", "/contact"]
    )
    def test_all_pages_load(self, fast_client: TestClient, path: str):
        """Test all main pages load successfully."""
        response = fast_client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_404_for_missing_page(self, fast_client: TestClient):
        """Test 404 for non-existent pages."""
        response = fast_client.get("/does-not-exist")
        assert response.status_code == 404


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
