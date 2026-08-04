import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from jinja2 import Environment, FileSystemLoader

from finbot.apps.cc.routes.challenges import _challenge_list_with_stats


def _challenge_stats(*completion_times: int | None) -> dict:
    challenge = SimpleNamespace(
        category="test",
        description="",
        detector_class="MissingDetector",
        difficulty="beginner",
        hints=None,
        id="test-challenge",
        is_active=True,
        labels=None,
        points=100,
        prerequisites=None,
        subcategory=None,
        title="Test Challenge",
    )
    progress_rows = [
        SimpleNamespace(
            attempts=1,
            completion_time_seconds=completion_time,
            hints_used=0,
            status="completed",
            user_id=f"user-{index}",
        )
        for index, completion_time in enumerate(completion_times)
    ]
    challenge_query = MagicMock()
    challenge_query.order_by.return_value.all.return_value = [challenge]
    progress_query = MagicMock()
    progress_query.filter.return_value.all.return_value = progress_rows
    db = MagicMock()
    db.query.side_effect = [challenge_query, progress_query]

    return _challenge_list_with_stats(db)[0]


def test_average_solve_time_includes_zero_and_excludes_missing_values() -> None:
    stats = _challenge_stats(0, 10, None)

    assert stats["completions"] == 3
    assert stats["avg_solve_seconds"] == 5


def test_zero_second_average_is_preserved() -> None:
    stats = _challenge_stats(0)

    assert stats["avg_solve_seconds"] == 0


def test_challenge_template_renders_zero_second_average() -> None:
    template_dir = Path(__file__).parents[4] / "finbot" / "apps" / "cc" / "templates"
    template = Environment(loader=FileSystemLoader(template_dir)).get_template(
        "pages/challenges.html"
    )
    stats = _challenge_stats(0)

    rendered = template.render(
        categories=["test"],
        challenges=[stats],
        coverage=[],
        difficulties=["beginner"],
        summary={
            "active": 1,
            "inactive": 0,
            "invalid_detectors": 1,
            "solved": 1,
            "total": 1,
            "unsolved": 0,
        },
        url_for=lambda *args, **kwargs: "/static",
        user=None,
    )

    assert re.search(r">\s*0m\s*<", rendered)
