# ============================================================
# File: finbot/aegis/simulator/mutation.py
# Purpose: Attack payload mutation engine (encoding, paraphrasing, obfuscation)
# Author: Jean Francois Regis MUKIZA
# GSoC Week: 5
# OWASP Category: ASI01 (Prompt Injection)
# ============================================================
"""Payload mutation engine for generating attack variants.

Transforms attack payloads to evade detection while preserving intent:
- Encoding variants (base64, hex, ROT13, URL)
- Semantic paraphrasing (synonym replacement, syntax variation)
- Identifier renaming (variable names, function names)
- Formatting variation (whitespace, comments, escaping)
"""

import base64
import hashlib
import logging
import re
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class MutationType(str, Enum):
    """Types of payload mutations."""

    BASE64_ENCODE = "base64_encode"
    HEX_ENCODE = "hex_encode"
    URL_ENCODE = "url_encode"
    ROT13 = "rot13"
    SYNONYM_REPLACE = "synonym_replace"
    IDENTIFIER_RENAME = "identifier_rename"
    WHITESPACE_VARIATION = "whitespace_variation"
    COMMENT_INJECTION = "comment_injection"


class PayloadMutator:
    """Generates attack payload variants through mutation."""

    def __init__(self):
        """Initialize mutator with synonym mappings."""
        self._synonyms = {
            "create": ["make", "add", "generate", "produce"],
            "delete": ["remove", "drop", "erase", "eliminate"],
            "update": ["modify", "change", "alter", "adjust"],
            "vendor": ["supplier", "provider", "partner"],
            "invoice": ["bill", "receipt", "statement"],
            "user": ["account", "player", "admin"],
            "data": ["information", "content", "payload"],
            "system": ["platform", "application", "framework"],
            "admin": ["administrator", "manager", "operator"],
            "bypass": ["circumvent", "skip", "evade"],
            "access": ["obtain", "retrieve", "acquire"],
        }

    def mutate_base64(self, payload: str) -> str:
        """Encode payload as base64.

        Args:
            payload: Original payload text

        Returns:
            Base64-encoded payload
        """
        return base64.b64encode(payload.encode()).decode()

    def mutate_hex(self, payload: str) -> str:
        """Encode payload as hexadecimal.

        Args:
            payload: Original payload text

        Returns:
            Hex-encoded payload
        """
        return payload.encode().hex()

    def mutate_url_encode(self, payload: str) -> str:
        """URL-encode payload.

        Args:
            payload: Original payload text

        Returns:
            URL-encoded payload
        """
        from urllib.parse import quote

        return quote(payload)

    def mutate_rot13(self, payload: str) -> str:
        """Apply ROT13 cipher to payload.

        Args:
            payload: Original payload text

        Returns:
            ROT13-transformed payload
        """
        result = []
        for char in payload:
            if "a" <= char <= "z":
                result.append(chr((ord(char) - ord("a") + 13) % 26 + ord("a")))
            elif "A" <= char <= "Z":
                result.append(chr((ord(char) - ord("A") + 13) % 26 + ord("A")))
            else:
                result.append(char)
        return "".join(result)

    def mutate_synonym_replace(self, payload: str) -> str:
        """Replace words with synonyms.

        Args:
            payload: Original payload text

        Returns:
            Payload with synonyms replaced
        """
        mutated = payload
        for original, synonyms in self._synonyms.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(original), re.IGNORECASE)
            matches = list(pattern.finditer(payload))

            if matches:
                # Use first synonym (could randomize in production)
                synonym = synonyms[0]
                # Preserve case of original
                if matches[0].group(0)[0].isupper():
                    synonym = synonym.capitalize()

                mutated = pattern.sub(synonym, mutated)

        return mutated

    def mutate_identifier_rename(self, payload: str) -> str:
        """Rename identifiers (variables, functions, etc.).

        Args:
            payload: Original payload text

        Returns:
            Payload with identifiers renamed
        """
        # Find common Python/JS identifiers and rename them
        # This is a simple implementation; production would be more sophisticated
        identifier_map = {}
        counter = 0

        def replace_identifier(match: re.Match) -> str:  # type: ignore
            nonlocal counter
            identifier = match.group(0)
            if identifier not in identifier_map:
                identifier_map[identifier] = f"var_{counter}"
                counter += 1
            return identifier_map[identifier]

        # Match Python/JS identifiers (alphanumeric + underscore, starting with letter or _)
        mutated = re.sub(r"\b[a-zA-Z_]\w*\b", replace_identifier, payload)
        return mutated

    def mutate_whitespace_variation(self, payload: str) -> str:
        """Add/remove whitespace to vary formatting.

        Args:
            payload: Original payload text

        Returns:
            Payload with whitespace variation
        """
        # Remove leading/trailing whitespace, then add random indentation
        lines = [line.strip() for line in payload.split("\n")]
        mutated = "\n    ".join(lines)  # Add 4-space indentation
        return mutated

    def mutate_comment_injection(self, payload: str) -> str:
        """Inject comments into payload to evade pattern matching.

        Args:
            payload: Original payload text

        Returns:
            Payload with injected comments
        """
        # Insert Python-style comments at line breaks
        lines = payload.split("\n")
        comments = [
            "# Processing",
            "# Executing",
            "# Continuing",
            "# Next step",
        ]

        mutated_lines = []
        for i, line in enumerate(lines):
            mutated_lines.append(line)
            if i < len(lines) - 1:  # Don't add comment after last line
                comment = comments[i % len(comments)]
                mutated_lines.append(comment)

        return "\n".join(mutated_lines)

    def generate_mutations(
        self,
        payload: str,
        mutation_types: Optional[list[MutationType]] = None,
        count: int = 5,
    ) -> list[str]:
        """Generate multiple payload mutations.

        Args:
            payload: Original payload
            mutation_types: Types of mutations to apply (default: all)
            count: Number of variants to generate

        Returns:
            List of mutated payloads
        """
        if mutation_types is None:
            mutation_types = list(MutationType)

        mutations = [payload]  # Include original

        for mutation_type in mutation_types:
            try:
                if mutation_type == MutationType.BASE64_ENCODE:
                    mutations.append(self.mutate_base64(payload))
                elif mutation_type == MutationType.HEX_ENCODE:
                    mutations.append(self.mutate_hex(payload))
                elif mutation_type == MutationType.URL_ENCODE:
                    mutations.append(self.mutate_url_encode(payload))
                elif mutation_type == MutationType.ROT13:
                    mutations.append(self.mutate_rot13(payload))
                elif mutation_type == MutationType.SYNONYM_REPLACE:
                    mutations.append(self.mutate_synonym_replace(payload))
                elif mutation_type == MutationType.IDENTIFIER_RENAME:
                    mutations.append(self.mutate_identifier_rename(payload))
                elif mutation_type == MutationType.WHITESPACE_VARIATION:
                    mutations.append(self.mutate_whitespace_variation(payload))
                elif mutation_type == MutationType.COMMENT_INJECTION:
                    mutations.append(self.mutate_comment_injection(payload))
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Mutation %s failed: %s",
                    mutation_type.value,
                    e,
                )

        # Return unique mutations, up to requested count
        unique_mutations = list(dict.fromkeys(mutations))
        return unique_mutations[:count]

    def get_mutation_hash(self, payload: str) -> str:
        """Get SHA256 hash of payload for deduplication.

        Args:
            payload: Payload text

        Returns:
            SHA256 hex digest
        """
        return hashlib.sha256(payload.encode()).hexdigest()
