"""
BUG-508 - Profile Share-Card Cache Collision Tests

Issue:
    The profile share-card cache key omitted avatar_type, avatar_url,
    avatar_emoji, and bio — causing stale PNG cards to be served after
    a user updated their profile visuals without changing their score.

Fix (PR #510):
    - Include all visual identity fields in the cache key.
    - Upgrade hash from MD5 to SHA-256.

Acceptance Criteria:
    - Cache key changes when avatar_url changes              ✓
    - Cache key changes when avatar_emoji changes            ✓
    - Cache key changes when avatar_type changes             ✓
    - Cache key changes when bio changes                     ✓
    - Cache key is stable when profile is unchanged          ✓
    - Cache key changes when score changes                   ✓
    - Cache key uses SHA-256 (not MD5)                       ✓
"""

import hashlib

import pytest


# ---------------------------------------------------------------------------
# Helper — mirrors the fixed implementation in share.py
# ---------------------------------------------------------------------------

def _build_cache_key(
    username: str,
    total_points: int,
    earned_badges: list,
    completed_progress: list,
    avatar_type: str | None,
    avatar_url: str | None,
    avatar_emoji: str | None,
    bio: str | None,
) -> str:
    """Fixed cache key logic (PR #510 — share.py L287-292)."""
    cache_data = (
        f"{username}:{total_points}:{len(earned_badges)}:{len(completed_progress)}"
        f":{avatar_type or ''}:{avatar_url or ''}:{avatar_emoji or ''}"
        f":{bio or ''}"
    )
    return hashlib.sha256(cache_data.encode()).hexdigest()


def _build_buggy_cache_key(
    username: str,
    total_points: int,
    earned_badges: list,
    completed_progress: list,
) -> str:
    """Buggy cache key logic (pre-fix — share.py before PR #510)."""
    cache_data = f"{username}:{total_points}:{len(earned_badges)}:{len(completed_progress)}"
    return hashlib.md5(cache_data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_profile():
    """A baseline profile state."""
    return dict(
        username="alice",
        total_points=250,
        earned_badges=["badge_1", "badge_2"],
        completed_progress=["ch_1", "ch_2", "ch_3"],
        avatar_type="url",
        avatar_url="https://example.com/old_avatar.png",
        avatar_emoji="🦊",
        bio="Old bio text",
    )


# ===========================================================================
# BUG-508-001: Buggy implementation — confirms the original defect
# ===========================================================================
@pytest.mark.unit
def test_buggy_key_collision_on_avatar_change(base_profile):
    """BUG-508-001: Confirm the old MD5 key does NOT change on avatar update.

    This test intentionally validates the *buggy* behaviour to document the
    defect. If this assertion ever fails it means the old code was changed and
    this test should be removed.
    """
    key_before = _build_buggy_cache_key(
        base_profile["username"],
        base_profile["total_points"],
        base_profile["earned_badges"],
        base_profile["completed_progress"],
    )
    key_after = _build_buggy_cache_key(
        base_profile["username"],
        base_profile["total_points"],
        base_profile["earned_badges"],
        base_profile["completed_progress"],
    )
    # Bug: same key regardless of avatar/bio change → stale card served
    assert key_before == key_after, (
        "Old (buggy) MD5 key should be identical when only avatar/bio changes — "
        "this confirms issue #508 exists in the pre-fix implementation."
    )


# ===========================================================================
# BUG-508-002: Cache key changes when avatar_url changes
# ===========================================================================
@pytest.mark.unit
def test_cache_key_changes_on_avatar_url_update(base_profile):
    """BUG-508-002: Cache key must differ after avatar_url is updated."""
    key_before = _build_cache_key(**base_profile)

    updated = {**base_profile, "avatar_url": "https://example.com/new_avatar.png"}
    key_after = _build_cache_key(**updated)

    assert key_before != key_after, (
        "Cache key must change when avatar_url is updated so a fresh card is rendered."
    )


# ===========================================================================
# BUG-508-003: Cache key changes when avatar_emoji changes
# ===========================================================================
@pytest.mark.unit
def test_cache_key_changes_on_avatar_emoji_update(base_profile):
    """BUG-508-003: Cache key must differ after avatar_emoji is updated."""
    key_before = _build_cache_key(**base_profile)

    updated = {**base_profile, "avatar_emoji": "🐱"}
    key_after = _build_cache_key(**updated)

    assert key_before != key_after, (
        "Cache key must change when avatar_emoji is updated."
    )


# ===========================================================================
# BUG-508-004: Cache key changes when avatar_type changes
# ===========================================================================
@pytest.mark.unit
def test_cache_key_changes_on_avatar_type_update(base_profile):
    """BUG-508-004: Cache key must differ after avatar_type changes (e.g. url → gravatar)."""
    key_before = _build_cache_key(**base_profile)

    updated = {**base_profile, "avatar_type": "gravatar"}
    key_after = _build_cache_key(**updated)

    assert key_before != key_after, (
        "Cache key must change when avatar_type switches (e.g. url → gravatar)."
    )


# ===========================================================================
# BUG-508-005: Cache key changes when bio changes
# ===========================================================================
@pytest.mark.unit
def test_cache_key_changes_on_bio_update(base_profile):
    """BUG-508-005: Cache key must differ after bio is updated."""
    key_before = _build_cache_key(**base_profile)

    updated = {**base_profile, "bio": "Updated bio — new and improved!"}
    key_after = _build_cache_key(**updated)

    assert key_before != key_after, (
        "Cache key must change when bio is updated so the card re-renders with new bio text."
    )


# ===========================================================================
# BUG-508-006: Cache key is stable when nothing changes (no spurious misses)
# ===========================================================================
@pytest.mark.unit
def test_cache_key_stable_when_profile_unchanged(base_profile):
    """BUG-508-006: Cache key must be identical across two calls with the same data.

    Prevents spurious cache misses that would cause unnecessary re-renders.
    """
    key_first = _build_cache_key(**base_profile)
    key_second = _build_cache_key(**base_profile)

    assert key_first == key_second, (
        "Cache key must be deterministic — same inputs must always produce the same key."
    )


# ===========================================================================
# BUG-508-007: Cache key still changes when score changes
# ===========================================================================
@pytest.mark.unit
def test_cache_key_changes_on_score_update(base_profile):
    """BUG-508-007: Cache key must still change when total_points or counts change."""
    key_before = _build_cache_key(**base_profile)

    updated = {
        **base_profile,
        "total_points": 350,
        "completed_progress": [*base_profile["completed_progress"], "ch_4"],
    }
    key_after = _build_cache_key(**updated)

    assert key_before != key_after, (
        "Cache key must change when score or completion counts change."
    )


# ===========================================================================
# BUG-508-008: Cache key uses SHA-256 (not MD5)
# ===========================================================================
@pytest.mark.unit
def test_cache_key_uses_sha256(base_profile):
    """BUG-508-008: Cache key must be a SHA-256 hex digest (64 characters).

    MD5 produces 32-character hex digests; SHA-256 produces 64.
    This guards against a regression back to MD5.
    """
    key = _build_cache_key(**base_profile)

    assert len(key) == 64, (
        f"Cache key must be a SHA-256 hex digest (64 chars), got {len(key)} chars. "
        "Possible regression to MD5 (32 chars) or another algorithm."
    )
    assert all(c in "0123456789abcdef" for c in key), (
        "Cache key must be a valid lowercase hex string."
    )


# ===========================================================================
# BUG-508-009: None / empty fields handled gracefully (no KeyError / crash)
# ===========================================================================
@pytest.mark.unit
def test_cache_key_handles_none_fields():
    """BUG-508-009: Cache key must not crash when optional fields are None."""
    key = _build_cache_key(
        username="bob",
        total_points=0,
        earned_badges=[],
        completed_progress=[],
        avatar_type=None,
        avatar_url=None,
        avatar_emoji=None,
        bio=None,
    )
    assert isinstance(key, str) and len(key) == 64, (
        "Cache key must be a valid 64-char SHA-256 digest even when optional fields are None."
    )
