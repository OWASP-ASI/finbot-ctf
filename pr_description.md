# Fix #547: Apply `parameters` override in `_apply_tool_overrides`

Closes #547

## What changed

`finbot/mcp/factory.py` - `_apply_tool_overrides`

Previously the function only read `description` from each tool override entry and silently discarded any `parameters` / `inputSchema` block the caller had stored.
This PR widens the implementation to also apply the parameter schema when one is present in the override dict.

## Why

The `PUT /darklab/api/v1/supply-chain/servers/{server_type}/tools` endpoint accepts and persists arbitrary JSON per tool (including `parameters`), the Dark Lab UI displays the full stored object, and the supply-chain stats endpoint counted parameter-bearing overrides as "poisoned tools" -- but the agent runtime never saw the changed schema. This created a silent mismatch between what was stored and what was actually active.

## Changes

### `finbot/mcp/factory.py`

```diff
-async def _apply_tool_overrides(server: FastMCP, overrides: dict) -> None:
-    """Apply user-supplied tool description overrides to a FastMCP server.
-
-    Modifies tool descriptions (the text the LLM sees) via the provider's
-    get_tool() API. This is the primary CTF attack surface for tool poisoning.
-    """
+async def _apply_tool_overrides(server: FastMCP, overrides: dict) -> None:
+    """Apply user-supplied tool overrides to a FastMCP server.
+
+    Supports two override keys per tool:
+    - description: replaces the natural-language description the LLM sees.
+    - parameters / inputSchema: replaces the JSON Schema used for arguments.
+
+    Fixes #547: previously only description was applied; parameters was
+    silently discarded even though the API accepted and stored it.
+    """
     ...
     for tool_name, override in overrides.items():
         new_description = override.get("description")
-        if new_description:
-            try:
-                tool = await provider.get_tool(tool_name)
-                if tool:
-                    tool.description = new_description
-            except Exception:
-                logger.debug("Tool '%s' not found for override", tool_name)
+        new_parameters = override.get("parameters") or override.get("inputSchema")
+
+        if not (new_description or new_parameters):
+            continue
+
+        try:
+            tool = await provider.get_tool(tool_name)
+            if tool:
+                if new_description:
+                    tool.description = new_description
+                if new_parameters:
+                    tool.inputSchema = new_parameters
+        except Exception:
+            logger.debug("Tool '%s' not found for override", tool_name)
```

## Behaviour preserved

- Description-only overrides work exactly as before.
- The `if not (new_description or new_parameters): continue` guard means entries with neither key are skipped, same as before.
- Accepts `parameters` (Dark Lab UI key) and `inputSchema` (FastMCP native key) interchangeably.

## Testing

Run the existing dark lab route security tests to confirm nothing regresses:

```bash
pytest tests/unit/apps/darklab/ -v
```

Manual verification:
1. PUT a tool override with both `description` and `parameters` for `finmail/send_email`
2. Trigger the agent to call `send_email`
3. Confirm the agent receives the modified parameter schema (e.g. `bcc` field is now known to the LLM)
