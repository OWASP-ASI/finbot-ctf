# fix: guardrail webhook sends invalid JSON on large payloads; `after_tool` skipped for `complete_task`

## Summary

This PR fixes two bugs in the FinBot Labs guardrail webhook system:

1. **Payload truncated mid-JSON before signing** — large guardrail hook payloads were being sliced at a raw byte offset, producing invalid JSON that the receiver could not parse, while the HMAC signature continued to validate correctly. The receiver had no way to detect this corruption.

2. **`after_tool` hook never fires for `complete_task`** — the agent loop returned immediately after `complete_task` succeeded, bypassing the corresponding `after_tool` invocation and leaving every `complete_task` call with an unmatched `before_tool` event.

---

## Problem 1 — Payload truncated mid-JSON

### Root Cause

In [`finbot/guardrails/service.py`](finbot/guardrails/service.py), the `invoke()` method serializes the full `HookEnvelope` to JSON bytes and then slices them at `LABS_GUARDRAIL_MAX_PAYLOAD_BYTES`:

```python
body_bytes = envelope.model_dump_json().encode()
if len(body_bytes) > max_payload:
    body_bytes = body_bytes[:max_payload]   # ← raw byte slice, breaks JSON
signature = self._sign_payload(body_bytes, ...)  # HMAC over broken bytes
```

A raw byte slice cuts the JSON in the middle of a field value. The result is syntactically invalid JSON (e.g. `..."model_output": "here is the ana`), but because the HMAC is computed over the same truncated bytes, the signature check on the receiver side passes — the corruption is completely invisible to the receiver.

### Fix

Truncation is moved **before serialization**, at the field level:

- Before calling `model_dump_json()`, we compute a tentative payload size.
- If it would exceed `max_payload`, we cap the long string fields (`model_output`, `tool_result`, `user_message`) inside the envelope so that re-serialization fits within the limit.
- The signed body is always valid, parseable JSON.
- Two new headers are added to the webhook request when truncation occurs:
  - `X-Guardrail-Truncated: true`
  - `X-Guardrail-Full-Size: <original_byte_count>`

This allows the receiver to detect truncation explicitly rather than hitting a `JSONDecodeError`.

### Files Changed

| File | Change |
|---|---|
| [`finbot/guardrails/service.py`](finbot/guardrails/service.py) | Replace raw byte slice with field-level truncation; add `X-Guardrail-Truncated` and `X-Guardrail-Full-Size` headers |

---

## Problem 2 — `after_tool` skipped for `complete_task`

### Root Cause

In [`finbot/agents/base.py`](finbot/agents/base.py), lines 152–189, the `before_tool` guardrail hook fires for every tool call, including `complete_task`. However, when `complete_task` succeeds, the agent loop returns immediately on line 174, **before** the `after_tool` invocation on line 183 is reached:

```python
await self._guardrail_service.invoke(HookKind.before_tool, ...)  # fires ✓

try:
    function_output = await callable_fn(**tool_call["arguments"])
    if tool_call_name == "complete_task":
        await self.log_task_completion(...)
        return function_output  # ← returns here, skips after_tool ✗

await self._guardrail_service.invoke(HookKind.after_tool, ...)  # never reached
```

Any guardrail that tracks paired `before_tool` / `after_tool` events (e.g. to measure tool execution time or audit a tool's output) will see every `complete_task` appear open-ended.

### Fix

The `after_tool` invocation is moved to execute **before** the early return for `complete_task`:

```python
function_output = await callable_fn(**tool_call["arguments"])
if tool_call_name == "complete_task":
    await self._guardrail_service.invoke(        # fires ✓ before return
        HookKind.after_tool,
        tool_name=tool_call_name,
        tool_source=tool_source,
        tool_arguments=tool_call.get("arguments"),
        tool_result=str(function_output),
    )
    await self.log_task_completion(task_result=function_output)
    return function_output
```

### Files Changed

| File | Change |
|---|---|
| [`finbot/agents/base.py`](finbot/agents/base.py) | Invoke `after_tool` guardrail hook before the early return for `complete_task` |

---

## Behaviour After This PR

| Scenario | Before | After |
|---|---|---|
| Large `after_model` payload exceeds limit | Receiver gets broken JSON; HMAC passes; parse fails silently | Receiver gets valid JSON with long fields truncated; `X-Guardrail-Truncated: true` header present |
| Large `after_tool` payload exceeds limit | Same as above | Same as above |
| `complete_task` tool call | `before_tool` fires, `after_tool` never fires | Both `before_tool` and `after_tool` fire |
| Normal-sized payload | Unchanged | Unchanged |

---

## Testing

- [ ] Set `LABS_GUARDRAIL_MAX_PAYLOAD_BYTES` to a small value (e.g. 500 bytes), trigger a long LLM response, and verify the webhook receives valid JSON with `X-Guardrail-Truncated: true`.
- [ ] Verify that the HMAC signature validates correctly against the truncated (but valid JSON) body.
- [ ] Trigger an agent run that finishes via `complete_task` and confirm both `before_tool` and `after_tool` events appear in the activity log for that call.
- [ ] Trigger a normal tool call (non-`complete_task`) and confirm no regression in `after_tool` behaviour.

---

## Affected Files

- [`finbot/guardrails/service.py`](finbot/guardrails/service.py) — `invoke()`, payload truncation logic (lines 119–132)
- [`finbot/agents/base.py`](finbot/agents/base.py) — `_run_agent_loop()`, `after_tool` hook for `complete_task` (lines 168–174)
