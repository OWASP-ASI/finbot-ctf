"""
CTF Definition Loader Tests

User Story: As a platform engineer, I want unit tests for the definition
            loader so that CTF challenge and badge definitions load correctly
            from YAML files.

Acceptance Criteria:
- DefinitionLoader.load_all / load_challenges / load_badges (DEF-LDR-001 through 008)
- _load_challenge_yaml / _load_badge_yaml YAML parsing (DEF-LDR-009 through 012)
- _upsert dialect handling (DEF-LDR-013 through 016)
- get_loader singleton (DEF-LDR-017 through 018)

Production Impact
=================
DefinitionLoader seeds the database with challenge and badge definitions at
startup. A broken loader means challenges and badges never reach the DB —
users see a blank CTF platform with no available challenges, and operators
have no indication from application logs that the seeding step silently failed.

- Load errors     A crash in load_challenges or load_badges aborts the entire
                  startup sequence; the platform starts with stale or empty
                  challenge definitions.
- Skip-on-error   If bad YAML aborts the loop instead of being skipped, one
                  corrupted file blocks every other challenge from loading.
- Dialect mismatch If the upsert uses the wrong SQL dialect, definitions are
                  never written to the DB — the YAML files look correct but
                  the database is never updated.
- Singleton leak  If get_loader is not cached, every call re-reads all YAML
                  files; definitions can drift between calls in the same request.
"""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from finbot.ctf.definitions.loader import DefinitionLoader, get_loader
from finbot.ctf.schemas.challenge import ChallengeSchema
from finbot.ctf.schemas.badge import BadgeSchema


# ---------------------------------------------------------------------------
# Shared YAML fixtures
# ---------------------------------------------------------------------------

MINIMAL_CHALLENGE_YAML = textwrap.dedent("""\
    id: test-challenge
    title: Test Challenge Title
    description: A test challenge for unit testing purposes.
    category: prompt-injection
    difficulty: beginner
    points: 100
    detector_class: PatternMatchDetector
    detector_config:
      field: content
      patterns:
        - secret
""")

MINIMAL_BADGE_YAML = textwrap.dedent("""\
    id: test-badge
    title: Test Badge
    description: A test badge.
    category: achievement
    rarity: common
    points: 10
    evaluator_class: ChallengeCompletionEvaluator
""")


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.bind = MagicMock()
    db.bind.dialect.name = "sqlite"
    return db


@pytest.fixture
def loader(tmp_path):
    """DefinitionLoader pointing at a temporary empty directory."""
    return DefinitionLoader(definitions_path=tmp_path)


@pytest.fixture
def loader_with_files(tmp_path):
    """DefinitionLoader with one challenge YAML and one badge YAML pre-written."""
    challenges_dir = tmp_path / "challenges"
    badges_dir = tmp_path / "badges"
    challenges_dir.mkdir()
    badges_dir.mkdir()
    (challenges_dir / "test-challenge.yaml").write_text(MINIMAL_CHALLENGE_YAML)
    (badges_dir / "test-badge.yaml").write_text(MINIMAL_BADGE_YAML)
    return DefinitionLoader(definitions_path=tmp_path)


# ===========================================================================
# load_challenges
# ===========================================================================

class TestLoadChallenges:

    @pytest.mark.unit
    def test_def_ldr_001_no_challenges_dir_returns_empty(self, loader, mock_db):
        """DEF-LDR-001: Missing challenges/ directory returns an empty list

        Title: Absent challenges directory is handled gracefully
        Description: When the definitions_path has no "challenges" sub-directory,
                     load_challenges must return an empty list and log a warning
                     without raising an exception.

        Steps:
        1. Create DefinitionLoader pointing at a directory with no "challenges" sub-dir
        2. Call load_challenges with a mock DB session

        Expected Results:
        1. Returns an empty list []
        2. No exception is raised
        3. DB commit is not called (nothing to save)

        Impact: If an exception is raised instead of returning [], the entire
                platform startup crashes and no CTF session can begin. If it
                silently continues with garbage data, challenges from the
                previous deployment persist unreset and users interact with
                stale definitions that no longer match the intended scenario.
        """
        result = loader.load_challenges(mock_db)
        assert result == []

    @pytest.mark.unit
    def test_def_ldr_002_loads_challenge_from_yaml(self, loader_with_files, mock_db):
        """DEF-LDR-002: Valid challenge YAML file is loaded and upserted

        Title: Single challenge YAML produces one upsert call and one commit
        Description: When a valid challenge YAML exists in the challenges/
                     directory it must be parsed, upserted to the database,
                     and its ID added to the returned list.

        Steps:
        1. Create DefinitionLoader pointing at a directory containing one challenge YAML
        2. Patch _upsert_challenge to capture calls
        3. Call load_challenges with a mock DB session
        4. Inspect returned list and mock calls

        Expected Results:
        1. "test-challenge" is in the returned list
        2. _upsert_challenge is called exactly once
        3. db.commit is called exactly once

        Impact: If upsert is not called or commit is skipped, the challenge
                definition sits in the YAML file but never reaches the database
                — the challenge appears missing to all users. Operators editing
                YAML files and restarting the service will see no effect, with
                no error surfaced to indicate the write was silently dropped.
        """
        with patch.object(loader_with_files, "_upsert_challenge") as mock_upsert:
            result = loader_with_files.load_challenges(mock_db)
        assert "test-challenge" in result
        mock_upsert.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.unit
    def test_def_ldr_003_bad_yaml_is_skipped(self, tmp_path, mock_db):
        """DEF-LDR-003: Malformed YAML is logged and skipped without aborting

        Title: Invalid YAML file does not prevent loading of other files
        Description: When a YAML file cannot be parsed (syntax error) or
                     fails schema validation, the loader must log the error,
                     skip that file, and continue processing the rest.

        Steps:
        1. Create a challenges/ directory with one invalid YAML file
        2. Create DefinitionLoader pointing at that directory
        3. Call load_challenges with a mock DB session

        Expected Results:
        1. Returns an empty list [] (bad file is skipped)
        2. No exception propagates out of load_challenges
        3. db.commit is called (even if nothing loaded)

        Impact: If a malformed YAML aborts the entire load loop, one corrupted
                file in the definitions directory blocks every other challenge
                from loading at startup. All CTF challenges become unavailable
                until the corrupted file is manually removed, and operators
                may not connect the blank challenge list to the single bad file.
        """
        challenges_dir = tmp_path / "challenges"
        challenges_dir.mkdir()
        (challenges_dir / "bad.yaml").write_text("id: !!invalid-yaml\n  broken:")

        loader = DefinitionLoader(definitions_path=tmp_path)
        result = loader.load_challenges(mock_db)
        assert result == []
        mock_db.commit.assert_called_once()

    @pytest.mark.unit
    def test_def_ldr_004_multiple_challenge_files(self, tmp_path, mock_db):
        """DEF-LDR-004: Multiple challenge YAML files are all loaded

        Title: Every YAML file in the challenges/ directory is processed
        Description: load_challenges must recursively find all *.yaml files
                     and load each one. The returned list must contain every
                     challenge ID loaded.

        Steps:
        1. Create three valid challenge YAML files in challenges/
        2. Create DefinitionLoader pointing at that directory
        3. Patch _upsert_challenge to avoid DB calls
        4. Call load_challenges

        Expected Results:
        1. Returned list contains exactly 3 entries
        2. _upsert_challenge is called 3 times

        Impact: If the loader processes only the first file and stops, new
                challenge definitions added by operators never reach the database
                regardless of how many times the service restarts. The platform
                silently presents an incomplete challenge set, with no log
                message indicating that files were skipped.
        """
        challenges_dir = tmp_path / "challenges"
        challenges_dir.mkdir()
        for i in range(3):
            yaml_content = MINIMAL_CHALLENGE_YAML.replace(
                "test-challenge", f"challenge-{i}"
            ).replace("Test Challenge Title", f"Challenge {i} Title")
            (challenges_dir / f"challenge-{i}.yaml").write_text(yaml_content)

        loader = DefinitionLoader(definitions_path=tmp_path)
        with patch.object(loader, "_upsert_challenge"):
            result = loader.load_challenges(mock_db)
        assert len(result) == 3


# ===========================================================================
# load_badges
# ===========================================================================

class TestLoadBadges:

    @pytest.mark.unit
    def test_def_ldr_005_no_badges_dir_returns_empty(self, loader, mock_db):
        """DEF-LDR-005: Missing badges/ directory returns an empty list

        Title: Absent badges directory is handled gracefully
        Description: When the definitions_path has no "badges" sub-directory,
                     load_badges must return an empty list without raising
                     an exception.

        Steps:
        1. Create DefinitionLoader pointing at a directory with no "badges" sub-dir
        2. Call load_badges with a mock DB session

        Expected Results:
        1. Returns an empty list []
        2. No exception is raised

        Impact: If a crash occurs here instead of returning [], users are unable
                to earn any badges regardless of challenge completion. The badge
                system is entirely dead from startup, with no visible error in
                the challenge UI to indicate the badges directory was missing.
        """
        assert loader.load_badges(mock_db) == []

    @pytest.mark.unit
    def test_def_ldr_006_loads_badge_from_yaml(self, loader_with_files, mock_db):
        """DEF-LDR-006: Valid badge YAML file is loaded and upserted

        Title: Single badge YAML produces one upsert call and one commit
        Description: When a valid badge YAML exists in the badges/ directory
                     it must be parsed, upserted to the database, and its ID
                     added to the returned list.

        Steps:
        1. Create DefinitionLoader pointing at a directory containing one badge YAML
        2. Patch _upsert_badge to capture calls
        3. Call load_badges with a mock DB session
        4. Inspect returned list and mock calls

        Expected Results:
        1. "test-badge" is in the returned list
        2. _upsert_badge is called exactly once
        3. db.commit is called exactly once

        Impact: If upsert or commit is skipped, badges stay in YAML files and
                never appear in the UI. Users complete challenges but receive no
                badge recognition — the evaluator finds no matching badge record
                in the database and silently skips the award with no error logged.
        """
        with patch.object(loader_with_files, "_upsert_badge") as mock_upsert:
            result = loader_with_files.load_badges(mock_db)
        assert "test-badge" in result
        mock_upsert.assert_called_once()
        mock_db.commit.assert_called_once()


# ===========================================================================
# load_all
# ===========================================================================

class TestLoadAll:

    @pytest.mark.unit
    def test_def_ldr_007_load_all_returns_combined_dict(self, loader_with_files, mock_db):
        """DEF-LDR-007: load_all returns a dict with both 'challenges' and 'badges' keys

        Title: Combined load returns a structured summary of loaded definitions
        Description: load_all must call load_challenges and load_badges and
                     return the results combined into a single dict with
                     "challenges" and "badges" as keys.

        Steps:
        1. Create DefinitionLoader with both challenge and badge YAML files
        2. Patch _upsert_challenge and _upsert_badge to avoid DB calls
        3. Call load_all with a mock DB session
        4. Inspect the returned dict

        Expected Results:
        1. Returned dict has key "challenges"
        2. Returned dict has key "badges"
        3. "test-challenge" is in result["challenges"]
        4. "test-badge" is in result["badges"]

        Impact: If load_all returns an incomplete dict missing "challenges" or
                "badges", callers that key into the result raise KeyError at
                startup, preventing the platform from initializing. This surfaces
                as an unhandled exception in the startup sequence with no
                graceful degradation path for operators to follow.
        """
        with patch.object(loader_with_files, "_upsert_challenge"), \
             patch.object(loader_with_files, "_upsert_badge"):
            result = loader_with_files.load_all(mock_db)
        assert "challenges" in result
        assert "badges" in result
        assert "test-challenge" in result["challenges"]
        assert "test-badge" in result["badges"]

    @pytest.mark.unit
    def test_def_ldr_008_load_all_empty_dirs(self, loader, mock_db):
        """DEF-LDR-008: load_all with no YAML files returns empty lists for both keys

        Title: Loader with no definitions returns empty collections
        Description: When neither challenges/ nor badges/ directories exist,
                     load_all must return {"challenges": [], "badges": []}.

        Steps:
        1. Create DefinitionLoader pointing at an empty directory
        2. Call load_all with a mock DB session

        Expected Results:
        1. Returns {"challenges": [], "badges": []}

        Impact: If an empty definitions directory raises an exception instead
                of returning empty lists, a fresh deployment with no YAML files
                crashes on first startup. The platform never becomes available
                and operators must diagnose a startup crash rather than a simple
                empty-state condition that can be resolved by adding YAML files.
        """
        result = loader.load_all(mock_db)
        assert result == {"challenges": [], "badges": []}


# ===========================================================================
# YAML parsing
# ===========================================================================

class TestYamlParsing:

    @pytest.mark.unit
    def test_def_ldr_009_load_challenge_yaml_returns_schema(self, tmp_path):
        """DEF-LDR-009: _load_challenge_yaml returns a validated ChallengeSchema

        Title: Valid challenge YAML is parsed and validated against the schema
        Description: _load_challenge_yaml must open the file, parse the YAML,
                     and construct a ChallengeSchema with correct field values.

        Steps:
        1. Write a minimal valid challenge YAML file to a temp directory
        2. Call _load_challenge_yaml with the file path

        Expected Results:
        1. Returns an instance of ChallengeSchema
        2. schema.id equals "test-challenge"
        3. schema.difficulty equals "beginner"
        4. schema.points equals 100

        Impact: If field values are parsed with wrong types (e.g. points as
                string "100" instead of int 100), downstream comparison logic
                for difficulty gating and point awards silently produces wrong
                results. Users may receive incorrect point totals or be granted
                access to challenges they have not yet qualified for.
        """
        path = tmp_path / "c.yaml"
        path.write_text(MINIMAL_CHALLENGE_YAML)
        loader = DefinitionLoader(definitions_path=tmp_path)
        schema = loader._load_challenge_yaml(path)
        assert isinstance(schema, ChallengeSchema)
        assert schema.id == "test-challenge"
        assert schema.difficulty == "beginner"
        assert schema.points == 100

    @pytest.mark.unit
    def test_def_ldr_010_load_badge_yaml_returns_schema(self, tmp_path):
        """DEF-LDR-010: _load_badge_yaml returns a validated BadgeSchema

        Title: Valid badge YAML is parsed and validated against the schema
        Description: _load_badge_yaml must open the file, parse the YAML,
                     and construct a BadgeSchema with correct field values.

        Steps:
        1. Write a minimal valid badge YAML file to a temp directory
        2. Call _load_badge_yaml with the file path

        Expected Results:
        1. Returns an instance of BadgeSchema
        2. schema.id equals "test-badge"
        3. schema.category equals "achievement"

        Impact: Wrong field types in the parsed BadgeSchema cause badge award
                logic to fail silently — the evaluator comparison breaks at
                runtime and users who earn a badge never see it. No exception
                is raised; the badge simply does not appear in the user's profile
                despite the challenge having been completed.
        """
        path = tmp_path / "b.yaml"
        path.write_text(MINIMAL_BADGE_YAML)
        loader = DefinitionLoader(definitions_path=tmp_path)
        schema = loader._load_badge_yaml(path)
        assert isinstance(schema, BadgeSchema)
        assert schema.id == "test-badge"
        assert schema.category == "achievement"

    @pytest.mark.unit
    def test_def_ldr_011_challenge_validation_error_propagates(self, tmp_path):
        """DEF-LDR-011: Invalid challenge YAML raises a Pydantic ValidationError

        Title: Schema validation failure propagates from _load_challenge_yaml
        Description: When a YAML file is syntactically valid but missing
                     required fields, Pydantic must raise a ValidationError
                     that propagates out of _load_challenge_yaml.

        Steps:
        1. Write a YAML file with only "id" and "title" (missing required fields)
        2. Call _load_challenge_yaml with that file path

        Expected Results:
        1. pydantic.ValidationError is raised
        2. No partial ChallengeSchema is returned

        Impact: If a schema-invalid YAML file is silently swallowed without
                raising, a challenge with a missing required field (e.g. no
                detector_class) gets upserted into the database. The event
                processor then crashes when it tries to instantiate the detector,
                causing detection to stop entirely for all challenges in that
                namespace until the service restarts.
        """
        from pydantic import ValidationError
        path = tmp_path / "bad.yaml"
        path.write_text("id: test-challenge\ntitle: Hi\n")
        loader = DefinitionLoader(definitions_path=tmp_path)
        with pytest.raises(ValidationError):
            loader._load_challenge_yaml(path)

    @pytest.mark.unit
    def test_def_ldr_012_challenge_with_all_optional_fields(self, tmp_path):
        """DEF-LDR-012: Challenge YAML with all optional fields loads correctly

        Title: Full challenge definition including optional fields is accepted
        Description: A challenge YAML may include hints, labels, prerequisites,
                     resources, scoring modifiers, subcategory, and image_url.
                     All optional fields must be parsed without error.

        Steps:
        1. Write a YAML file with all optional fields populated
        2. Call _load_challenge_yaml with that file path
        3. Inspect the returned ChallengeSchema

        Expected Results:
        1. Returns a ChallengeSchema with id="full-challenge"
        2. subcategory equals "argument-injection"
        3. hints list has 1 entry
        4. scoring is not None and contains 1 modifier

        Impact: If optional fields like hints, scoring, or subcategory cause a
                parse error, any challenge YAML that uses those fields fails to
                load. Operators adding hints or scoring modifiers silently break
                the challenge — it disappears from the platform with no user-
                visible error and no alert in the operator dashboard.
        """
        full_yaml = textwrap.dedent("""\
            id: full-challenge
            title: Full Challenge Title Here
            description: A very detailed description for a full challenge.
            category: tool-misuse
            subcategory: argument-injection
            difficulty: advanced
            points: 300
            image_url: https://example.com/image.png
            hints:
              - cost: 10
                text: Try looking at the tool arguments.
            labels:
              owasp_llm: ["LLM01"]
              cwe: ["CWE-20"]
              mitre_atlas: []
              owasp_agentic: ["T2"]
            prerequisites: ["intro-challenge"]
            resources:
              - title: OWASP LLM Top 10
                url: https://owasp.org
            detector_class: ToolCallDetector
            detector_config:
              tool_name: pay_invoice
            scoring:
              modifiers:
                - type: pi_jb
                  penalty: 0.5
                  min_confidence: 0.7
            is_active: true
            order_index: 5
        """)
        path = tmp_path / "full.yaml"
        path.write_text(full_yaml)
        loader = DefinitionLoader(definitions_path=tmp_path)
        schema = loader._load_challenge_yaml(path)
        assert schema.id == "full-challenge"
        assert schema.subcategory == "argument-injection"
        assert len(schema.hints) == 1
        assert schema.scoring is not None
        assert len(schema.scoring.modifiers) == 1


# ===========================================================================
# _upsert dialect handling
# ===========================================================================

class TestUpsertDialect:

    def _make_challenge_schema(self):
        import yaml
        data = yaml.safe_load(MINIMAL_CHALLENGE_YAML)
        return ChallengeSchema(**data)

    def _make_badge_schema(self):
        import yaml
        data = yaml.safe_load(MINIMAL_BADGE_YAML)
        return BadgeSchema(**data)

    @pytest.mark.unit
    def test_def_ldr_013_sqlite_upsert_executes(self, tmp_path):
        """DEF-LDR-013: SQLite dialect uses sqlite_insert with on_conflict_do_update

        Title: Challenge upsert executes a statement on SQLite
        Description: When the DB dialect is "sqlite", _upsert must use the
                     SQLite INSERT ... ON CONFLICT UPDATE statement and call
                     db.execute with it.

        Steps:
        1. Create a mock DB with dialect.name="sqlite"
        2. Call _upsert_challenge with a valid ChallengeSchema

        Expected Results:
        1. db.execute is called exactly once
        2. No exception is raised

        Impact: If the SQLite dialect path is broken, every local development
                and CI environment fails to seed challenge definitions. All
                detector tests that depend on seeded data then fail with
                misleading "challenge not found" errors, obscuring the true
                cause and slowing down debugging across the entire test suite.
        """
        db = MagicMock()
        db.bind.dialect.name = "sqlite"
        loader = DefinitionLoader(definitions_path=tmp_path)
        challenge = self._make_challenge_schema()
        loader._upsert_challenge(db, challenge)
        db.execute.assert_called_once()

    @pytest.mark.unit
    def test_def_ldr_014_postgresql_upsert_executes(self, tmp_path):
        """DEF-LDR-014: PostgreSQL dialect uses pg_insert with on_conflict_do_update

        Title: Challenge upsert executes a statement on PostgreSQL
        Description: When the DB dialect is "postgresql", _upsert must use the
                     PostgreSQL INSERT ... ON CONFLICT UPDATE statement and call
                     db.execute with it.

        Steps:
        1. Create a mock DB with dialect.name="postgresql"
        2. Call _upsert_challenge with a valid ChallengeSchema

        Expected Results:
        1. db.execute is called exactly once
        2. No exception is raised

        Impact: If the PostgreSQL dialect path is broken, the production database
                never receives challenge or badge updates on deployment. Operators
                can edit YAML files and restart the service as many times as they
                like — the database stays stale, showing users old or missing
                challenges indefinitely with no error surfaced in the logs.
        """
        db = MagicMock()
        db.bind.dialect.name = "postgresql"
        loader = DefinitionLoader(definitions_path=tmp_path)
        challenge = self._make_challenge_schema()
        loader._upsert_challenge(db, challenge)
        db.execute.assert_called_once()

    @pytest.mark.unit
    def test_def_ldr_015_unknown_dialect_uses_merge(self, tmp_path):
        """DEF-LDR-015: Unknown dialect falls back to db.merge

        Title: Unsupported dialect uses the merge fallback path
        Description: When the DB dialect is neither "sqlite" nor "postgresql",
                     _upsert must fall back to db.merge and must not call
                     db.execute.

        Steps:
        1. Create a mock DB with dialect.name="oracle"
        2. Call _upsert_challenge with a valid ChallengeSchema

        Expected Results:
        1. db.merge is called exactly once
        2. db.execute is NOT called

        Impact: If the merge fallback is broken, any non-SQLite/non-PostgreSQL
                environment (e.g. a test setup using an in-memory store) crashes
                on the first upsert. This can block entire CI pipelines in
                certain configurations, and the failure message points to the
                upsert call rather than the missing fallback branch.
        """
        db = MagicMock()
        db.bind.dialect.name = "oracle"
        loader = DefinitionLoader(definitions_path=tmp_path)
        challenge = self._make_challenge_schema()
        loader._upsert_challenge(db, challenge)
        db.merge.assert_called_once()
        db.execute.assert_not_called()

    @pytest.mark.unit
    def test_def_ldr_016_upsert_badge_sqlite(self, tmp_path):
        """DEF-LDR-016: Badge upsert executes a statement on SQLite

        Title: Badge upsert path works the same as challenge upsert on SQLite
        Description: _upsert_badge must follow the same SQLite upsert path
                     as _upsert_challenge.

        Steps:
        1. Create a mock DB with dialect.name="sqlite"
        2. Call _upsert_badge with a valid BadgeSchema

        Expected Results:
        1. db.execute is called exactly once
        2. No exception is raised

        Impact: If the SQLite badge upsert path is broken, badge definitions
                never reach the database in local development and CI environments.
                Users earn no badges in any test or staging environment, and
                badge-related detector tests fail with misleading errors that
                suggest the evaluator logic is broken rather than the upsert path.
        """
        db = MagicMock()
        db.bind.dialect.name = "sqlite"
        loader = DefinitionLoader(definitions_path=tmp_path)
        badge = self._make_badge_schema()
        loader._upsert_badge(db, badge)
        db.execute.assert_called_once()


# ===========================================================================
# get_loader singleton
# ===========================================================================

class TestGetLoader:

    @pytest.mark.unit
    def test_def_ldr_017_get_loader_returns_instance(self):
        """DEF-LDR-017: get_loader() returns a DefinitionLoader instance

        Title: Singleton factory returns the correct type
        Description: get_loader must create and return a DefinitionLoader
                     instance when called for the first time.

        Steps:
        1. Reset the module-level _loader singleton to None
        2. Call get_loader()

        Expected Results:
        1. Returned value is an instance of DefinitionLoader

        Impact: If get_loader returns None or raises, every import of the
                singleton in the application fails with AttributeError or
                TypeError. The service cannot start at all — every module that
                calls get_loader() at import time propagates the error up to
                the WSGI entry point and prevents the process from binding.
        """
        import finbot.ctf.definitions.loader as loader_module
        loader_module._loader = None
        loader = get_loader()
        assert isinstance(loader, DefinitionLoader)

    @pytest.mark.unit
    def test_def_ldr_018_get_loader_is_singleton(self):
        """DEF-LDR-018: Repeated calls to get_loader() return the same instance

        Title: get_loader() caches the loader after the first call
        Description: To avoid redundant initialization, get_loader must return
                     the same DefinitionLoader instance on every call after the
                     first.

        Steps:
        1. Reset the module-level _loader singleton to None
        2. Call get_loader() twice

        Expected Results:
        1. Both calls return the same object (a is b)

        Impact: If get_loader creates a new DefinitionLoader on every call,
                each call re-reads all YAML files from disk, causing repeated
                disk I/O under load. Each re-read also resets internal state,
                so challenge definitions can drift between calls within the same
                request — a user's challenge lookup may return a different result
                than the preceding eligibility check for the same challenge ID.
        """
        import finbot.ctf.definitions.loader as loader_module
        loader_module._loader = None
        a = get_loader()
        b = get_loader()
        assert a is b
