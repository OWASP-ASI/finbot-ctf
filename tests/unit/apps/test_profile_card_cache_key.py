# Tests for finbot.apps.ctf.routes.share._profile_card_cache_key (issue #508).
#
# Bug: the profile share-card cache key was built from only 4 fields
# (username, total_points, badges_earned, challenges_completed). Two users
# sharing the same stats (extremely common at 0/0/0 on registration)
# collided on the identical cache file; whichever rendered first was
# permanently served to the other. Same-user avatar/bio changes were also
# invisible to the cache -- the old card stayed stale until stats changed.
#
# Also caught before writing the fix: the linked issue's own suggested fix
# (adding avatar_type/avatar_url/avatar_emoji/bio to the key) has a real
# gap -- resolve_avatar_url() (finbot/apps/ctf/routes/profile.py) resolves
# the actual rendered image from user.email, not profile.avatar_url, when
# avatar_type == "gravatar". A cache key missing user.email would still
# collide for two gravatar-type profiles with matching stats and no bio,
# even after applying the issue's own proposed fix verbatim.

import pytest

from finbot.apps.ctf.routes.share import _profile_card_cache_key


def _key(**overrides):
    defaults = dict(
        username="alice",
        total_points=100,
        badges_earned=2,
        challenges_completed=3,
        avatar_type="emoji",
        avatar_url=None,
        avatar_emoji="🦊",
        user_email="alice@example.com",
        bio="hi",
        earned_badge_ids=["badge_a", "badge_b"],
        featured_badge_ids=["badge_a"],
    )
    defaults.update(overrides)
    return _profile_card_cache_key(**defaults)


class TestProfileCardCacheKey:

    @pytest.mark.unit
    def test_deterministic_for_identical_inputs(self):
        assert _key() == _key()

    @pytest.mark.unit
    def test_different_usernames_produce_different_keys(self):
        assert _key(username="alice") != _key(username="bob")

    @pytest.mark.unit
    def test_two_users_with_matching_stats_and_different_avatar_url_do_not_collide(self):
        """The core bug: two users at identical stats (common at 0/0/0)
        must not map to the same cache file just because points/badges/
        challenges match -- their actual rendered avatar differs."""
        key_a = _key(
            username="alice", total_points=0, badges_earned=0, challenges_completed=0,
            avatar_type="url", avatar_url="https://example.com/a.png",
        )
        key_b = _key(
            username="bob", total_points=0, badges_earned=0, challenges_completed=0,
            avatar_type="url", avatar_url="https://example.com/b.png",
        )
        assert key_a != key_b

    @pytest.mark.unit
    def test_avatar_url_change_invalidates_the_cache_key(self):
        """Same user, same stats, changed avatar -- must get a new key,
        not silently serve the old cached card forever."""
        before = _key(avatar_type="url", avatar_url="https://example.com/old.png")
        after = _key(avatar_type="url", avatar_url="https://example.com/new.png")
        assert before != after

    @pytest.mark.unit
    def test_bio_change_invalidates_the_cache_key(self):
        before = _key(bio="old bio")
        after = _key(bio="new bio")
        assert before != after

    @pytest.mark.unit
    def test_avatar_emoji_change_invalidates_the_cache_key(self):
        before = _key(avatar_type="emoji", avatar_emoji="🦊")
        after = _key(avatar_type="emoji", avatar_emoji="🐱")
        assert before != after

    @pytest.mark.unit
    def test_gravatar_users_with_different_emails_do_not_collide(self):
        """The gap in the linked issue's own suggested fix: for
        avatar_type == "gravatar", the rendered image comes from
        user.email (see resolve_avatar_url), not from avatar_url. Two
        profiles with identical stats, avatar_type="gravatar", and no
        avatar_url/bio set would still collide without user_email in the
        key -- exactly the scenario the issue's own diff would have
        missed."""
        key_a = _key(
            avatar_type="gravatar", avatar_url=None, bio=None,
            user_email="alice@example.com",
        )
        key_b = _key(
            avatar_type="gravatar", avatar_url=None, bio=None,
            user_email="bob@example.com",
        )
        assert key_a != key_b

    @pytest.mark.unit
    def test_none_values_do_not_raise(self):
        _profile_card_cache_key(
            username="alice",
            total_points=0,
            badges_earned=0,
            challenges_completed=0,
            avatar_type=None,
            avatar_url=None,
            avatar_emoji=None,
            user_email=None,
            bio=None,
            earned_badge_ids=[],
            featured_badge_ids=[],
        )  # must not raise

    @pytest.mark.unit
    def test_returns_a_hex_digest(self):
        key = _key()
        assert isinstance(key, str)
        int(key, 16)  # must be valid hex

    @pytest.mark.unit
    def test_re_curating_featured_badges_invalidates_the_cache_key(self):
        """PUT /featured-badges lets a user change which earned badges are
        featured with zero change to total_points/badges_earned/
        challenges_completed -- must not leave the card stale."""
        before = _key(
            earned_badge_ids=["a", "b", "c"], featured_badge_ids=["a", "b"]
        )
        after = _key(
            earned_badge_ids=["a", "b", "c"], featured_badge_ids=["b", "c"]
        )
        assert before != after

    @pytest.mark.unit
    def test_featured_badge_order_change_invalidates_the_cache_key(self):
        """The card renders featured badges in the user's chosen order --
        a reorder with the same set must still bust the cache."""
        before = _key(featured_badge_ids=["a", "b"])
        after = _key(featured_badge_ids=["b", "a"])
        assert before != after

    @pytest.mark.unit
    def test_earned_badge_composition_change_at_same_count_invalidates_the_key(self):
        """Losing one badge and gaining a different one at the same total
        count must still bust the cache -- badges_earned alone (a count)
        can't distinguish this, and the composition change can also
        silently change which badge is "latest"."""
        before = _key(badges_earned=2, earned_badge_ids=["a", "b"])
        after = _key(badges_earned=2, earned_badge_ids=["a", "c"])
        assert before != after

    @pytest.mark.unit
    def test_earned_badge_order_does_not_matter_only_composition(self):
        """Unlike featured badges, earned badges aren't displayed in a
        user-chosen order on the card -- only which badges are earned
        matters, so the key should be stable under reordering."""
        key_a = _key(earned_badge_ids=["a", "b", "c"])
        key_b = _key(earned_badge_ids=["c", "a", "b"])
        assert key_a == key_b
