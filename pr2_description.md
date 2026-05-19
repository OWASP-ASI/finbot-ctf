## Summary

Fixes two key security issues in the authentication layer:
- Email format validation on the magic-link endpoint.
- Per-IP rate limiting on the magic-link endpoint.

> [!NOTE]
> **Finding 3 (Insecure `DEBUG` Default) Excluded:** After thorough evaluation, changing the default configuration fallback to `DEBUG=False` has been intentionally omitted from this PR. Changing it to `False` by default breaks local Capture-the-Flag (CTF) environments out of the box (e.g., SSRF validation strictly blocks `localhost` and private IP webhooks when `DEBUG` is `False`). To maintain an excellent local developer/player experience while preserving safety, `DEBUG` remains `True` by default, and production environments should continue to explicitly override it using `DEBUG=false` in their `.env` file as documented.

Fixes issue #___ *(link the GitHub issue for Finding 1–2 here)*

---

## Changes

### `finbot/apps/finbot/auth.py`

**1. Email format validation** — Rejects non-email strings before hitting the DB or email service.

```diff
+ from pydantic import EmailStr, ValidationError
+
  email = email.lower().strip()
+
+ try:
+     EmailStr._validate(email)
+ except Exception:
+     return template_response(request, "auth-error.html", {
+         "error": "Invalid email",
+         "message": "Please enter a valid email address.",
+     })
```

**2. Per-IP rate limiting** — Sliding-window counter (5 req / 60 s) using only stdlib.
No new dependencies added. Comment in code explains how to upgrade to Redis-backed `slowapi` for multi-worker deployments.

```diff
+ _RATE_LIMIT_WINDOW = 60
+ _RATE_LIMIT_MAX    = 5
+ _rate_store: dict[str, list[float]] = defaultdict(list)
+ _rate_lock = Lock()
+
+ def _is_rate_limited(ip: str) -> bool: ...
+
  client_ip = request.client.host if request.client else "unknown"
+ if _is_rate_limited(client_ip):
+     return template_response(request, "auth-error.html", {
+         "error": "Too many requests",
+         "message": "Please wait a moment before requesting another sign-in link.",
+     })
```

---

## Why This Matters

| Before | After | Risk Removed |
|--------|-------|-------------|
| Any string accepted as email | Validated against RFC 5321 format | Orphaned DB rows, email service errors, unhandled exception leaks |
| No throttle on magic-link endpoint | 5 req/min per IP | Email flooding, inbox harassment, database DoS |

---

## Testing

- [x] `POST /auth/magic-link` with `email=not-an-email` → returns validation error page
- [x] `POST /auth/magic-link` called 6× in under 60 s from same IP → 6th request returns rate-limit error page
- [x] Valid email still works end-to-end (magic link sent, token stored)

---

## Notes for Reviewers

- **Rate limiter is in-memory per-process.** For a multi-worker Gunicorn setup this should be upgraded to a Redis-backed limiter. A `# TODO` comment is left in code.
- **`pydantic[email]`** is already listed in `pyproject.toml` — no new dependency added.
- **DEBUG status preserved:** The `DEBUG` default in `config.py` was kept as `True` to ensure local CTF challenge compatibility.
