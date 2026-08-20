# Tests for ToolOverridesUpdate's parameters-shape validation (issue #547).
#
# Complements tests/unit/mcp/test_factory.py, which covers the runtime
# application side (_apply_tool_overrides silently rejecting a bad schema
# rather than letting it later crash tool listing). This covers the write
# boundary: reject a malformed override at request time with a clear 422,
# rather than accepting it into the DB and deferring the failure to an
# unrelated future request.

import pytest
from pydantic import ValidationError

from finbot.apps.darklab.routes.api import ToolOverridesUpdate


class TestToolOverridesUpdateValidation:

    @pytest.mark.unit
    def test_accepts_valid_description_only_override(self):
        ToolOverridesUpdate(tool_overrides={"send_email": {"description": "x"}})

    @pytest.mark.unit
    def test_accepts_valid_parameters_override(self):
        ToolOverridesUpdate(
            tool_overrides={
                "send_email": {"parameters": {"type": "object", "properties": {}}}
            }
        )

    @pytest.mark.unit
    def test_accepts_valid_inputschema_override(self):
        ToolOverridesUpdate(
            tool_overrides={"send_email": {"inputSchema": {"type": "object"}}}
        )

    @pytest.mark.unit
    def test_accepts_empty_dict_parameters(self):
        """A deliberate {} override (stripping every param) is a valid,
        meaningful override -- must not be rejected."""
        ToolOverridesUpdate(tool_overrides={"send_email": {"parameters": {}}})

    @pytest.mark.unit
    def test_rejects_non_dict_parameters(self):
        with pytest.raises(ValidationError, match="parameters"):
            ToolOverridesUpdate(
                tool_overrides={"send_email": {"parameters": "not a dict"}}
            )

    @pytest.mark.unit
    def test_rejects_non_dict_inputschema(self):
        with pytest.raises(ValidationError, match="inputSchema"):
            ToolOverridesUpdate(
                tool_overrides={"send_email": {"inputSchema": ["not", "a", "dict"]}}
            )

    @pytest.mark.unit
    def test_rejects_non_dict_override_entry(self):
        """A whole tool's override being a non-object (e.g. a bare
        string) must be rejected at write time -- not silently skipped,
        since that would let malformed structure into the DB that later
        crashes _apply_tool_overrides when applied."""
        with pytest.raises(ValidationError, match="object"):
            ToolOverridesUpdate(tool_overrides={"send_email": "not even a dict"})

    @pytest.mark.unit
    def test_rejects_non_string_description(self):
        with pytest.raises(ValidationError, match="description"):
            ToolOverridesUpdate(tool_overrides={"send_email": {"description": 12345}})

    @pytest.mark.unit
    def test_rejects_non_dict_parameters_among_multiple_tools(self):
        """A bad override anywhere in the batch is rejected -- not just
        silently skipped while the rest apply."""
        with pytest.raises(ValidationError):
            ToolOverridesUpdate(
                tool_overrides={
                    "send_email": {"description": "fine"},
                    "delete_file": {"parameters": 42},
                }
            )
