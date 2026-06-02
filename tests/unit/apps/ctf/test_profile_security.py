"""Unit tests for CTF profile security and validation checks"""

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from finbot.apps.ctf.routes.profile import update_profile, ProfileUpdateRequest
from finbot.core.auth.session import SessionContext


@pytest.fixture
def mock_session_context():
    """Mock session context for an authenticated user"""
    context = MagicMock(spec=SessionContext)
    context.user_id = "test_user_id"
    return context


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock()


@pytest.fixture
def mock_profile_repo():
    """Mock profile repository"""
    return MagicMock()


@pytest.fixture
def patch_dependencies(monkeypatch, mock_profile_repo):
    """Patch the UserProfileRepository, validate_username, and _update_social_links"""
    monkeypatch.setattr(
        "finbot.apps.ctf.routes.profile.UserProfileRepository",
        lambda db, context: mock_profile_repo,
    )
    monkeypatch.setattr(
        "finbot.apps.ctf.routes.profile.validate_username",
        lambda username: (True, None),
    )
    monkeypatch.setattr(
        "finbot.apps.ctf.routes.profile._update_social_links",
        lambda profile, request, db: None,
    )
    monkeypatch.setattr(
        "finbot.apps.ctf.routes.profile._build_profile_response",
        lambda profile, user: MagicMock(),
    )


@pytest.mark.asyncio
async def test_update_profile_avatar_url_valid_https(
    mock_session_context, mock_db, mock_profile_repo, patch_dependencies
):
    """Test that a valid HTTPS URL is accepted during profile update"""
    # Arrange
    existing_profile = MagicMock()
    existing_profile.avatar_type = "url"
    existing_profile.avatar_url = "https://example.com/old.png"
    existing_profile.user_id = "test_user_id"
    mock_profile_repo.get_by_user_id.return_value = existing_profile

    updated_profile = MagicMock()
    mock_profile_repo.update_profile.return_value = updated_profile

    request = ProfileUpdateRequest(
        avatar_type="url",
        avatar_url="https://example.com/new.png"
    )

    # Act
    response = await update_profile(
        request=request,
        session_context=mock_session_context,
        db=mock_db
    )

    # Assert
    assert response is not None
    mock_profile_repo.update_profile.assert_called_once()


@pytest.mark.asyncio
async def test_update_profile_avatar_url_insecure_blocked(
    mock_session_context, mock_db, mock_profile_repo, patch_dependencies
):
    """Test that an insecure HTTP URL is blocked when avatar_type is explicitly 'url'"""
    # Arrange
    existing_profile = MagicMock()
    existing_profile.avatar_type = "url"
    existing_profile.avatar_url = "https://example.com/old.png"
    existing_profile.user_id = "test_user_id"
    mock_profile_repo.get_by_user_id.return_value = existing_profile

    request = ProfileUpdateRequest(
        avatar_type="url",
        avatar_url="http://127.0.0.1/malicious.png"
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await update_profile(
            request=request,
            session_context=mock_session_context,
            db=mock_db
        )
    
    assert exc_info.value.status_code == 400
    assert "Invalid Avatar URL: Only public HTTPS URLs are allowed" in exc_info.value.detail
    mock_profile_repo.update_profile.assert_not_called()


@pytest.mark.asyncio
async def test_update_profile_avatar_url_bypass_attempt_blocked(
    mock_session_context, mock_db, mock_profile_repo, patch_dependencies
):
    """Test that omitting avatar_type still blocks insecure URLs if the database type is 'url'"""
    # Arrange
    existing_profile = MagicMock()
    existing_profile.avatar_type = "url"
    existing_profile.avatar_url = "https://example.com/old.png"
    existing_profile.user_id = "test_user_id"
    mock_profile_repo.get_by_user_id.return_value = existing_profile

    # request omits 'avatar_type', but tries to inject insecure 'avatar_url'
    request = ProfileUpdateRequest(
        avatar_url="http://169.254.169.254/latest/meta-data"
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await update_profile(
            request=request,
            session_context=mock_session_context,
            db=mock_db
        )
    
    assert exc_info.value.status_code == 400
    assert "Invalid Avatar URL: Only public HTTPS URLs are allowed" in exc_info.value.detail
    mock_profile_repo.update_profile.assert_not_called()


@pytest.mark.asyncio
async def test_update_profile_avatar_url_emoji_retains_insecure_url_ignored(
    mock_session_context, mock_db, mock_profile_repo, patch_dependencies
):
    """Test that changing avatar_type to emoji clears/ignores insecure URL checks"""
    # Arrange
    existing_profile = MagicMock()
    existing_profile.avatar_type = "url"
    existing_profile.avatar_url = "https://example.com/old.png"
    existing_profile.user_id = "test_user_id"
    mock_profile_repo.get_by_user_id.return_value = existing_profile

    updated_profile = MagicMock()
    mock_profile_repo.update_profile.return_value = updated_profile

    # User changes type to emoji, URL should no longer trigger validation error even if old url was insecure
    request = ProfileUpdateRequest(
        avatar_type="emoji",
        avatar_emoji="🦊"
    )

    # Act
    response = await update_profile(
        request=request,
        session_context=mock_session_context,
        db=mock_db
    )

    # Assert
    assert response is not None
    mock_profile_repo.update_profile.assert_called_once_with(
        user_id="test_user_id",
        bio=None,
        avatar_emoji="🦊",
        avatar_type="emoji",
        avatar_url=None,
        is_public=None,
        show_activity=None
    )


@pytest.mark.asyncio
async def test_update_profile_avatar_url_ssrf_blocked(
    mock_session_context, mock_db, mock_profile_repo, patch_dependencies
):
    """Test that a private IP is blocked even if it uses HTTPS"""
    # Arrange
    existing_profile = MagicMock()
    existing_profile.avatar_type = "url"
    existing_profile.avatar_url = "https://example.com/old.png"
    existing_profile.user_id = "test_user_id"
    mock_profile_repo.get_by_user_id.return_value = existing_profile

    request = ProfileUpdateRequest(
        avatar_type="url",
        avatar_url="https://127.0.0.1/malicious.png"
    )

    # Act & Assert
    with pytest.raises(HTTPException) as exc_info:
        await update_profile(
            request=request,
            session_context=mock_session_context,
            db=mock_db
        )
    
    assert exc_info.value.status_code == 400
    assert "Invalid Avatar URL: Only public HTTPS URLs are allowed" in exc_info.value.detail
    mock_profile_repo.update_profile.assert_not_called()
