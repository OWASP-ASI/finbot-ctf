# fix(security): Block SSRF in guardrail webhook URL and require authentication on write endpoints

Fixes #535

## Summary

The FinBot Labs guardrail webhook configuration API (`/labs/api/v1/guardrails`) allowed any **anonymous (temp-session) user** to register an arbitrary URL as their webhook target. Because the server-side `GuardrailHookService` fires an HTTP POST to that URL on every hook invocation - and a `/test` endpoint lets the caller trigger one immediately - this was a fully exploitable **unauthenticated SSRF** that could reach Redis, Postgres, cloud metadata endpoints (AWS IMDS), and any other host reachable from the server.

## Root Cause

Two independent weaknesses combined to create the vulnerability:

| # | File | Problem |
|---|------|---------|
| 1 | `finbot/apps/labs/routes/guardrails.py` | All write endpoints (`PUT`, `POST /toggle`, `POST /rotate-secret`, `DELETE`, `POST /test`) used `get_session_context`, which accepts anonymous temporary sessions |
| 2 | `finbot/apps/labs/routes/guardrails.py` | `webhook_url` was only validated for `max_length=2048` - no scheme or IP filtering at all |

`validate_webhook_url()` already existed in the codebase for config validation but was never applied at the route layer.

## Changes - `finbot/apps/labs/routes/guardrails.py`

### 1. SSRF blocklist applied to `webhook_url` before storing

```python
# Before
class GuardrailConfigRequest(BaseModel):
    webhook_url: str = Field(max_length=2048)  # no URL validation

# After - validation at the route level, before any DB write
ok, err_msg = validate_webhook_url(body.webhook_url)
if not ok:
    raise HTTPException(
        status_code=422,
        detail=f"Invalid webhook URL: {err_msg}",
    )
```

`validate_webhook_url()` resolves the hostname via DNS and rejects:
- Loopback addresses (`127.x.x.x`, `::1`)
- Private ranges (RFC 1918: `10.*`, `172.16-31.*`, `192.168.*`)
- Link-local addresses (`169.254.*`, `fe80::`)
- Any non-`http(s)` scheme

### 2. All write endpoints require an authenticated (email-bound) session

```python
# Before (all 5 write endpoints)
session_context: SessionContext = Depends(get_session_context)   # anonymous OK

# After
session_context: SessionContext = Depends(get_authenticated_session_context)  # login required
```

Endpoints changed:
- `PUT /labs/api/v1/guardrails` - upsert config
- `POST /labs/api/v1/guardrails/toggle` - enable/disable
- `POST /labs/api/v1/guardrails/rotate-secret` - rotate HMAC secret
- `DELETE /labs/api/v1/guardrails` - delete config
- `POST /labs/api/v1/guardrails/test` - fire test hook

The **read-only** endpoints (`GET /labs/api/v1/guardrails` and `GET /labs/api/v1/guardrails/activity`) remain accessible to temp sessions - they return `null` / empty arrays for users with no config, which is safe.

## What Was NOT Changed

- `validate_webhook_url()` itself - reused as-is from `finbot/core/data/repositories.py`
- `GuardrailHookService` - no changes needed; the URL is validated before it ever reaches the service
- All read endpoints - still use `get_session_context` (no sensitive write operations)

## Attack Scenarios Blocked

| Before fix | After fix |
|------------|-----------|
| Anonymous user sets `webhook_url = "http://127.0.0.1:6379/"` | 422 - blocked by SSRF check |
| Authenticated user sets `webhook_url = "http://10.0.0.1/admin"` | 422 - private IP blocked |
| Anonymous user calls `/test` to trigger SSRF | 401 - auth required |
| `http://169.254.169.254/latest/meta-data/` (AWS IMDS) | 422 - link-local blocked |

## Tests

### New - Route-level security tests

**`tests/unit/labs/test_guardrail_route_security.py`** (new file, covers the exact lines changed by this PR)

| Test class | What it asserts |
|---|---|
| `TestGuardrailWriteEndpointsRequireAuth` | All 5 write endpoints (`PUT`, `POST /toggle`, `POST /rotate-secret`, `DELETE`, `POST /test`) return **401** for anonymous (temp) sessions. `GET` still returns 200. |
| `TestGuardrailWebhookUrlSsrfValidation` | 7 private/internal URLs each return **422** when submitted by an authenticated user (loopback IPv4/IPv6, RFC-1918, link-local/AWS IMDS). A public URL is accepted. |

Run:
```bash
pytest tests/unit/labs/test_guardrail_route_security.py -v
```

### Existing - Repository / validator tests (no changes needed)

`tests/unit/labs/test_guardrail_config.py` already covers:
- `validate_webhook_url()` allows/blocks URLs correctly (production vs debug mode)
- Repo-level `upsert()` raises `ValueError` for private IPs
- Full CRUD, namespace isolation, toggle, rotate-secret

Those tests are **not modified** - they remain green as the underlying repository logic is unchanged.

### Manual smoke test
```bash
# Anonymous → 401
curl -X PUT http://localhost:8000/labs/api/v1/guardrails \
  -b "finbot_session=<temp-session>" \
  -H "Content-Type: application/json" \
  -d '{"webhook_url": "https://webhook.site/test", "enabled": true}'
# → 401

# Private IP (auth'd) → 422
curl -X PUT http://localhost:8000/labs/api/v1/guardrails \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -b "finbot_session=<auth-session>" \
  -d '{"webhook_url": "http://127.0.0.1:6379/", "enabled": true}'
# → 422 Invalid webhook URL: only public HTTPS URLs are allowed ...

# Public URL (auth'd) → 200
curl -X PUT http://localhost:8000/labs/api/v1/guardrails \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <token>" \
  -b "finbot_session=<auth-session>" \
  -d '{"webhook_url": "https://webhook.site/my-id", "enabled": true}'
# → 200 OK
```

## Checklist

- [x] Fixes #535
- [x] SSRF blocklist applied via existing `validate_webhook_url()` utility - no new logic
- [x] All write endpoints now require authenticated session
- [x] Read-only endpoints (`GET`) unchanged - no regression for anonymous users
- [x] Route-level tests added (`test_guardrail_route_security.py`) - 401 + 422 cases
- [x] Existing repo-level tests unmodified and still pass
- [x] No database schema changes
- [x] No migration required
