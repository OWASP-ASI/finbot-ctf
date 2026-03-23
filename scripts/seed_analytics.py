"""
Seed Analytics Data

Populates the page_views table with realistic mock pageview data and
creates mock UserProfile records for testing the Command Center analytics
dashboard and social/profile features.

Audience: Development/testing only.

Usage:
    python scripts/seed_analytics.py            # ~2500 pageviews over 30 days
    python scripts/seed_analytics.py --days 14  # 14 days of data
    python scripts/seed_analytics.py --clear    # wipe existing data first
"""

import argparse
import hashlib
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from finbot.core.analytics import models as _analytics_models  # noqa: F401
from finbot.core.analytics.models import PageView
from finbot.core.data import models as _data_models  # noqa: F401
from finbot.core.data.models import User, UserProfile
from finbot.core.data.database import SessionLocal, create_tables

MOCK_USERNAMES = ["yello", "hackr42", "ctfpro", "nullbyte", "0xdead"]
MOCK_BADGE_IDS = [
    "first-blood", "renaissance-hacker", "goal-hijacker",
    "puppet-master", "wrecking-ball", "policy-architect",
]

PATHS = [
    ("/", 30),
    ("/portals", 25),
    ("/about", 12),
    ("/stats", 6),
    ("/agreement", 10),
    ("/auth/magic-link", 15),
    ("/auth/verify", 10),
    ("/ctf", 14),
    ("/ctf/challenges", 12),
    ("/ctf/badges", 8),
    ("/ctf/activity", 6),
    ("/ctf/profile/settings", 5),
    ("/vendor/dashboard", 8),
    ("/vendor/settings", 3),
    ("/admin/dashboard", 3),
    ("/api/session/status", 6),
    ("/demo/cineflow", 1),
]

SHARE_PATHS = [
    (lambda: f"/ctf/h/{random.choice(MOCK_USERNAMES)}", 6),
    (lambda: f"/ctf/share/profile/{random.choice(MOCK_USERNAMES)}/card.png", 4),
    (lambda: f"/ctf/share/badge/{random.choice(MOCK_BADGE_IDS)}/card.png", 3),
    (lambda: f"/ctf/api/v1/profile/u/{random.choice(MOCK_USERNAMES)}", 5),
]

BROWSERS = [
    ("Chrome", 50),
    ("Firefox", 18),
    ("Safari", 20),
    ("Edge", 8),
    ("Opera", 3),
    ("Arc", 1),
]

OSES = [
    ("Windows 10", 30),
    ("macOS 14", 25),
    ("Linux", 12),
    ("iOS 17", 18),
    ("Android 14", 12),
    ("ChromeOS", 3),
]

DEVICES = [
    ("desktop", 55),
    ("mobile", 35),
    ("tablet", 10),
]

REFERER_DOMAINS = [
    (None, 40),
    ("google.com", 20),
    ("github.com", 12),
    ("owasp.org", 10),
    ("twitter.com", 6),
    ("linkedin.com", 5),
    ("reddit.com", 4),
    ("bing.com", 3),
]

SESSION_TYPES = [
    ("perm", 60),
    ("temp", 40),
]


def weighted_choice(items: list[tuple]) -> any:
    values, weights = zip(*items)
    return random.choices(values, weights=weights, k=1)[0]


def make_session_id() -> str:
    return hashlib.sha256(random.randbytes(16)).hexdigest()[:32]


def make_user_agent(browser: str, os_name: str) -> str:
    ua_map = {
        "Chrome": f"Mozilla/5.0 ({os_name}) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Firefox": f"Mozilla/5.0 ({os_name}; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Safari": f"Mozilla/5.0 ({os_name}) AppleWebKit/605.1.15 Version/17.3 Safari/605.1.15",
        "Edge": f"Mozilla/5.0 ({os_name}) AppleWebKit/537.36 Chrome/122.0 Safari/537.36 Edg/122.0",
        "Opera": f"Mozilla/5.0 ({os_name}) AppleWebKit/537.36 Chrome/122.0 Safari/537.36 OPR/108.0",
        "Arc": f"Mozilla/5.0 ({os_name}) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36 Arc/1.0",
    }
    return ua_map.get(browser, f"Mozilla/5.0 ({os_name})")


def generate_pageviews(days: int = 30, base_daily: int = 80) -> list[PageView]:
    """Generate a list of PageView records spanning `days` with realistic patterns."""
    now = datetime.now(UTC)
    records = []

    sessions = [make_session_id() for _ in range(120)]

    for day_offset in range(days, 0, -1):
        day_base = now - timedelta(days=day_offset)

        # Traffic ramp-up: more recent days get more traffic
        recency_factor = 1 + (days - day_offset) / days
        weekday = day_base.weekday()
        weekend_factor = 0.6 if weekday >= 5 else 1.0
        daily_count = int(base_daily * recency_factor * weekend_factor * random.uniform(0.7, 1.3))

        for _ in range(daily_count):
            hour = random.choices(
                range(24),
                weights=[
                    1, 1, 1, 1, 1, 2,        # 00-05: low
                    3, 5, 7, 9, 10, 10,      # 06-11: morning ramp
                    9, 10, 11, 10, 9, 8,     # 12-17: afternoon peak
                    7, 6, 5, 4, 3, 2,        # 18-23: evening decline
                ],
                k=1,
            )[0]
            minute = random.randint(0, 59)
            second = random.randint(0, 59)
            ts = day_base.replace(hour=hour, minute=minute, second=second, microsecond=0)

            if random.random() < 0.08:
                share_fn = weighted_choice(SHARE_PATHS)
                path = share_fn()
            else:
                path = weighted_choice(PATHS)
            browser = weighted_choice(BROWSERS)
            os_name = weighted_choice(OSES)
            device = weighted_choice(DEVICES)
            referer_domain = weighted_choice(REFERER_DOMAINS)
            session_type = weighted_choice(SESSION_TYPES)
            session_id = random.choice(sessions)

            status = random.choices(
                [200, 301, 302, 304, 400, 403, 404, 500],
                weights=[85, 2, 3, 3, 2, 1, 3, 1],
                k=1,
            )[0]

            # Response time: most fast, some slow (simulates real distribution)
            if path.startswith("/api/"):
                base_rt = random.gauss(25, 15)
            elif path.startswith("/ctf/"):
                base_rt = random.gauss(80, 40)
            else:
                base_rt = random.gauss(45, 25)
            # Occasional slow outlier
            if random.random() < 0.05:
                base_rt *= random.uniform(3, 8)
            response_time = max(5, int(base_rt))

            referer = f"https://{referer_domain}/search" if referer_domain else None

            records.append(PageView(
                timestamp=ts,
                path=path,
                method="GET",
                status_code=status,
                response_time_ms=response_time,
                session_id=session_id,
                session_type=session_type,
                user_agent=make_user_agent(browser, os_name),
                browser=browser,
                os=os_name,
                device_type=device,
                referer=referer,
                referer_domain=referer_domain,
            ))

    return records


MOCK_PROFILES = [
    {
        "username": "hackr42", "bio": "Red teamer by day, CTF player by night",
        "avatar_emoji": "💀", "is_public": True, "show_activity": True,
        "social_github": "https://github.com/hackr42",
        "social_twitter": "https://twitter.com/hackr42",
    },
    {
        "username": "ctfpro", "bio": "OWASP contributor | AI security researcher",
        "avatar_emoji": "🎯", "is_public": True, "show_activity": False,
        "social_github": "https://github.com/ctfpro",
        "social_linkedin": "https://linkedin.com/in/ctfpro",
    },
    {
        "username": "nullbyte", "bio": None,
        "avatar_emoji": "🔓", "is_public": True, "show_activity": False,
    },
    {
        "username": "0xdead", "bio": "Just here for the badges",
        "avatar_emoji": "☠️", "is_public": False, "show_activity": False,
        "social_website": "https://0xdead.dev",
    },
]


def seed_profiles(db):
    """Create mock UserProfile records linked to mock users."""
    existing_users = {u.display_name: u for u in db.query(User).all()}

    created_users = 0
    created_profiles = 0

    for p in MOCK_PROFILES:
        username = p["username"]

        if username not in existing_users:
            user = User(
                user_id=f"user_{hashlib.md5(username.encode()).hexdigest()[:16]}",
                email=f"{username}@example.com",
                display_name=username,
                namespace=f"ns_{username}",
                is_active=True,
            )
            db.add(user)
            db.flush()
            existing_users[username] = user
            created_users += 1

        user = existing_users[username]

        existing_profile = (
            db.query(UserProfile)
            .filter(UserProfile.user_id == user.user_id)
            .first()
        )
        if existing_profile:
            continue

        profile = UserProfile(
            user_id=user.user_id,
            username=p["username"],
            bio=p.get("bio"),
            avatar_emoji=p.get("avatar_emoji", "🦊"),
            avatar_type="emoji",
            is_public=p.get("is_public", True),
            show_activity=p.get("show_activity", False),
            social_github=p.get("social_github"),
            social_twitter=p.get("social_twitter"),
            social_linkedin=p.get("social_linkedin"),
            social_website=p.get("social_website"),
            featured_badge_ids='["first-blood", "goal-hijacker"]' if random.random() > 0.5 else None,
        )
        db.add(profile)
        created_profiles += 1

    db.commit()
    print(f"Seeded {created_users} mock users, {created_profiles} profiles")


def main():
    parser = argparse.ArgumentParser(description="Seed analytics mock data")
    parser.add_argument("--days", type=int, default=30, help="Days of data to generate (default: 30)")
    parser.add_argument("--daily", type=int, default=80, help="Base daily pageview count (default: 80)")
    parser.add_argument("--clear", action="store_true", help="Delete all existing pageviews first")
    args = parser.parse_args()

    create_tables()

    db = SessionLocal()
    try:
        if args.clear:
            deleted = db.query(PageView).delete()
            db.commit()
            print(f"Cleared {deleted} existing pageviews")

        existing = db.query(PageView).count()
        print(f"Existing pageviews: {existing}")

        records = generate_pageviews(days=args.days, base_daily=args.daily)
        db.bulk_save_objects(records)
        db.commit()

        total = db.query(PageView).count()
        print(f"Inserted {len(records)} mock pageviews ({total} total)")

        seed_profiles(db)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
