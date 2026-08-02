from unittest.mock import MagicMock

from finbot.mcp.servers.finmail.routing import MAX_RECIPIENTS, route_and_deliver


def _route_email(
    to: list[str],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> tuple[dict, MagicMock, MagicMock]:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    repo = MagicMock()

    result = route_and_deliver(
        db=db,
        repo=repo,
        namespace="test",
        to=to,
        subject="Recipient limit test",
        body="Test body",
        cc=cc,
        bcc=bcc,
    )
    return result, db, repo


def test_route_and_deliver_rejects_recipient_count_above_limit() -> None:
    recipients = [f"recipient-{index}@example.com" for index in range(100)]

    result, db, repo = _route_email(to=recipients)

    assert result == {"error": f"Recipient count 100 exceeds maximum of {MAX_RECIPIENTS}"}
    db.query.assert_not_called()
    repo.create_email.assert_not_called()


def test_route_and_deliver_counts_to_cc_and_bcc_together() -> None:
    to = [f"to-{index}@example.com" for index in range(10)]
    cc = [f"cc-{index}@example.com" for index in range(10)]
    bcc = ["bcc@example.com"]

    result, db, repo = _route_email(to=to, cc=cc, bcc=bcc)

    assert result == {"error": f"Recipient count 21 exceeds maximum of {MAX_RECIPIENTS}"}
    db.query.assert_not_called()
    repo.create_email.assert_not_called()


def test_route_and_deliver_allows_recipient_count_at_limit() -> None:
    recipients = [f"recipient-{index}@test.finbot" for index in range(MAX_RECIPIENTS)]

    result, _, repo = _route_email(to=recipients)

    assert result["sent"] is True
    assert len(result["deliveries"]) == MAX_RECIPIENTS
    assert result["delivery_count"] == MAX_RECIPIENTS
    assert repo.create_email.call_count == MAX_RECIPIENTS
