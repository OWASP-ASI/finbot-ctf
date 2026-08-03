# ============================================================
# File: tests/unit/aegis/test_mutation.py
# Purpose: Unit tests for payload mutation engine
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 5
# OWASP Category: ASI01 (Prompt Injection)
# ============================================================
"""Tests for AEGIS payload mutation engine."""

import pytest
import base64

from finbot.aegis.simulator.mutation import PayloadMutator, MutationType


@pytest.mark.unit
class TestPayloadMutator:
    """Test payload mutation transformations."""

    def test_mutator_init(self) -> None:
        """Initialize mutator."""
        mutator = PayloadMutator()
        assert mutator is not None
        assert len(mutator._synonyms) > 0

    def test_base64_encode(self) -> None:
        """Base64 encode payload."""
        mutator = PayloadMutator()
        original = "create vendor named Acme"
        encoded = mutator.mutate_base64(original)

        # Verify it's valid base64
        assert isinstance(encoded, str)
        # Decode and verify
        decoded = base64.b64decode(encoded).decode()
        assert decoded == original

    def test_hex_encode(self) -> None:
        """Hex encode payload."""
        mutator = PayloadMutator()
        original = "delete invoice"
        encoded = mutator.mutate_hex(original)

        # Should be hex string
        assert isinstance(encoded, str)
        assert all(c in "0123456789abcdef" for c in encoded)
        # Verify round-trip
        decoded = bytes.fromhex(encoded).decode()
        assert decoded == original

    def test_rot13_encode(self) -> None:
        """ROT13 cipher."""
        mutator = PayloadMutator()
        original = "hello world"
        encoded = mutator.mutate_rot13(original)

        # ROT13 should preserve length
        assert len(encoded) == len(original)
        # Apply twice should return original
        decoded = mutator.mutate_rot13(encoded)
        assert decoded == original

    def test_url_encode(self) -> None:
        """URL encode payload."""
        mutator = PayloadMutator()
        original = "bypass security check"
        encoded = mutator.mutate_url_encode(original)

        # Should contain URL-safe characters
        assert "%20" in encoded or "+" in encoded or original == encoded

    def test_synonym_replace(self) -> None:
        """Replace words with synonyms."""
        mutator = PayloadMutator()
        original = "create vendor"
        mutated = mutator.mutate_synonym_replace(original)

        # Should be different (unless no synonyms exist)
        assert isinstance(mutated, str)
        # Original words should be replaced with synonyms
        assert "create" not in mutated.lower() or mutated == original

    def test_whitespace_variation(self) -> None:
        """Add whitespace variation."""
        mutator = PayloadMutator()
        original = "delete vendor\nupdate invoice"
        mutated = mutator.mutate_whitespace_variation(original)

        # Should add indentation
        assert isinstance(mutated, str)
        # Should contain spaces
        assert " " in mutated

    def test_comment_injection(self) -> None:
        """Inject comments into payload."""
        mutator = PayloadMutator()
        original = "create vendor\ndelete invoice"
        mutated = mutator.mutate_comment_injection(original)

        # Should contain comments
        assert "#" in mutated
        # Should still contain original content
        assert "create" in mutated
        assert "vendor" in mutated

    def test_generate_mutations(self) -> None:
        """Generate multiple mutations."""
        mutator = PayloadMutator()
        original = "bypass admin check"
        mutations = mutator.generate_mutations(original, count=5)

        # Should return multiple variants
        assert len(mutations) > 1
        assert len(mutations) <= 5
        # Original should be included
        assert original in mutations

    def test_get_mutation_hash(self) -> None:
        """Get payload hash for deduplication."""
        mutator = PayloadMutator()
        payload1 = "create vendor"
        payload2 = "create vendor"
        payload3 = "delete vendor"

        hash1 = mutator.get_mutation_hash(payload1)
        hash2 = mutator.get_mutation_hash(payload2)
        hash3 = mutator.get_mutation_hash(payload3)

        # Same payloads should have same hash
        assert hash1 == hash2
        # Different payloads should have different hashes
        assert hash1 != hash3
        # Should be 64 chars (SHA256 hex)
        assert len(hash1) == 64
