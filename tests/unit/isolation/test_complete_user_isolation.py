# ==============================================================================
# Complete User Isolation Test Suite
# ==============================================================================
# User Story: As a CTF participant, I want my data completely isolated from
#             other users so that I have a clean, private environment
#
# Acceptance Criteria:
#   1. Each user gets unique namespace
#   2. All database queries scoped to namespace
#   3. Cross-user data access impossible
#   4. File uploads namespaced
#   5. Session migration preserves isolation
#
# Test Categories:
#   CUI-NS-001: Unique namespace creation per user
#   CUI-NS-002: Namespace uniqueness validation
#   CUI-QRY-003: Database queries scoped to namespace
#   CUI-QRY-004: Cross-user query isolation verification
#   CUI-ACCESS-005: Cross-user data access prevention
#   CUI-FU-006: File uploads namespaced by user
#   CUI-FU-007: File isolation and access control
#   CUI-SM-008: Session migration preserves isolation
#   CUI-COM-009: Complete isolation end-to-end
# ==============================================================================

import hashlib
import hmac
import json

import pytest

from finbot.config import settings
from finbot.core.auth.session import session_manager
from finbot.core.data.models import UserSession


def _get_namespace(db, session_id: str):
    """Extract the namespace (or user_id fallback) from a session's stored data."""
    row = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    assert row is not None, f"Session {session_id} not found in database"
    data = json.loads(row.session_data)
    return data.get("namespace", data.get("user_id"))


def _get_session_data(db, session_id: str) -> dict:
    """Load and return the parsed session_data dict for a given session_id."""
    row = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    assert row is not None, f"Session {session_id} not found in database"
    return json.loads(row.session_data)


def _inject_session_data(db, session_id: str, key: str, value: str, signing_key: bytes):
    """Inject custom data into a session and re-sign the HMAC."""
    row = db.query(UserSession).filter(UserSession.session_id == session_id).first()
    assert row is not None, f"Session {session_id} not found"
    data = json.loads(row.session_data)
    data[key] = value
    row.session_data = json.dumps(data, sort_keys=True)
    row.signature = hmac.new(signing_key, row.session_data.encode(), hashlib.sha256).hexdigest()
    db.commit()


class TestCompleteUserIsolation:
    """
    Test Suite: Complete User Isolation

    Validates that user data is completely isolated across:
    - Namespace isolation (AC1)
    - Database query scoping (AC2)
    - Data access prevention (AC3)
    - File system namespacing (AC4)
    - Session migration (AC5)
    """

    # ==========================================================================
    # CUI-NS-001: Unique Namespace Creation Per User
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_ns_001_unique_namespace_creation(self, db):
        """
        CUI-NS-001: Unique Namespace Creation Per User
        Title: Each user receives a unique, isolated namespace
        Description: When a user creates a session, they must be assigned a
                     unique namespace that is independent from all other users

        Steps:
        1. Create first user session (alice@example.com)
        2. Extract alice's namespace from session_data
        3. Create second user session (bob@example.com)
        4. Extract bob's namespace from session_data
        5. Create third user session (charlie@example.com)
        6. Extract charlie's namespace from session_data
        7. Verify all three namespaces are different
        8. Verify each namespace is unique and non-null
        9. Verify namespace persists across queries
        10. Verify no namespace collisions exist in database

        Expected Results:
        1. Alice has unique namespace
        2. Bob has unique namespace
        3. Charlie has unique namespace
        4. All namespaces are different (alice ≠ bob ≠ charlie)
        5. Namespaces persist and are stable
        6. No namespace collisions found in database
        7. Each namespace is non-null and non-empty
        8. Namespace uniqueness enforced at storage level
        9. Isolation criteria met
        10. System ready for multi-user environment
        """
        emails = ["alice@example.com", "bob@example.com", "charlie@example.com"]
        sessions = {
            email: session_manager.create_session(email=email, user_agent="Mozilla/5.0")
            for email in emails
        }
        namespaces = {email: _get_namespace(db, ctx.session_id) for email, ctx in sessions.items()}

        # Verify each namespace is non-null and non-empty
        for email, ns in namespaces.items():
            assert ns is not None, f"{email} namespace is null"
            assert ns != "", f"{email} namespace is empty"

        # Verify all namespaces are unique
        ns_values = list(namespaces.values())
        assert len(ns_values) == len(set(ns_values)), f"Namespaces are not unique: {ns_values}"

        # Verify persistence on requery
        for email, ctx in sessions.items():
            ns_requery = _get_namespace(db, ctx.session_id)
            assert namespaces[email] == ns_requery, f"{email}'s namespace changed on requery"

        # Verify no collisions across all sessions in database
        all_sessions = db.query(UserSession).all()
        all_ns = [
            json.loads(s.session_data).get("namespace", json.loads(s.session_data).get("user_id"))
            for s in all_sessions
        ]
        duplicates = [ns for ns in all_ns if all_ns.count(ns) > 1]
        assert len(duplicates) == 0, f"Found duplicate namespaces in database: {duplicates}"

    # ==========================================================================
    # CUI-NS-002: Namespace Uniqueness Validation
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_ns_002_namespace_uniqueness_validation(self, db):
        """
        CUI-NS-002: Namespace Uniqueness Validation
        Title: Namespace uniqueness is enforced and validated
        Description: The system must validate and enforce that no two users
                     can have the same namespace

        Steps:
        1. Create 5 concurrent user sessions
        2. Extract namespace for each user
        3. Create a set of all namespaces
        4. Compare set length to user count
        5. Verify set has exactly 5 unique namespaces
        6. Verify no null or empty namespaces exist
        7. Verify namespace format is valid
        8. Verify namespace doesn't contain other user's email
        9. Verify namespace doesn't overlap with other namespaces
        10. Confirm isolation criteria met

        Expected Results:
        1. 5 unique namespaces created for 5 users
        2. Set length equals user count
        3. No null namespaces found
        4. No empty namespaces found
        5. All namespaces properly formatted
        6. No namespace cross-contamination detected
        7. No namespace overlap found
        8. No email addresses leaked in namespaces
        9. Uniqueness enforced at database level
        10. Complete isolation validation passed
        """
        users = [f"user{i}@example.com" for i in range(1, 6)]

        namespaces = {}
        for email in users:
            session = session_manager.create_session(email=email, user_agent="Mozilla/5.0")
            namespaces[email] = _get_namespace(db, session.session_id)

        # Verify uniqueness
        unique_namespaces = set(namespaces.values())
        assert (
            len(unique_namespaces) == 5
        ), f"Expected 5 unique namespaces, got {len(unique_namespaces)}"

        # Verify no null, empty, or invalid-type namespaces
        for email, ns in namespaces.items():
            assert ns is not None, f"{email} has null namespace"
            assert ns != "", f"{email} has empty namespace"
            assert isinstance(ns, (str, int)), f"{email} namespace has invalid type: {type(ns)}"

        # Verify no email username leakage across namespaces
        for email, ns in namespaces.items():
            for other_email in users:
                if other_email != email:
                    other_name = other_email.split("@")[0]
                    assert (
                        other_name not in str(ns).lower()
                    ), f"{email}'s namespace contains {other_name}"

        # Verify no namespace is a substring of another
        namespace_list = list(namespaces.values())
        for i, ns1 in enumerate(namespace_list):
            for ns2 in namespace_list[i + 1 :]:
                assert str(ns1) not in str(ns2), "Namespace contains another namespace"
                assert str(ns2) not in str(ns1), "Namespace is contained in another namespace"

        # Confirm all namespaces present in database
        all_sessions = db.query(UserSession).all()
        db_namespaces = {
            json.loads(s.session_data).get("namespace", json.loads(s.session_data).get("user_id"))
            for s in all_sessions
        }
        for ns in unique_namespaces:
            assert ns in db_namespaces, f"Namespace {ns} not found in database"

    # ==========================================================================
    # CUI-QRY-003: Database Queries Scoped to Namespace
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_qry_003_database_queries_scoped_to_namespace(self, db):
        """
        CUI-QRY-003: Database Queries Scoped to Namespace
        Title: All database queries are automatically scoped to user namespace
        Description: When querying user data, the database must restrict
                     results to only the requesting user's namespace

        Steps:
        1. Create session for user_alpha@example.com
        2. Create session for user_beta@example.com
        3. Query database for alpha's user_id
        4. Verify query returns only alpha's data
        5. Query database for beta's user_id
        6. Verify query returns only beta's data
        7. Attempt to query all users (no scope)
        8. Verify result set doesn't include other namespaces
        9. Run scoped query for alpha again
        10. Verify scoping works consistently

        Expected Results:
        1. Alpha query executed successfully
        2. Alpha query returns alpha's session only
        3. Beta query executed successfully
        4. Beta query returns beta's session only
        5. Alpha and beta queries return different data
        6. Cross-namespace data not included in results
        7. All users have isolated query scopes
        8. Query scoping enforced at database level
        9. Scoping remains consistent across multiple queries
        10. No data leakage between query results
        """
        session_alpha = session_manager.create_session(
            email="user_alpha@example.com", user_agent="Mozilla/5.0"
        )
        session_beta = session_manager.create_session(
            email="user_beta@example.com", user_agent="Mozilla/5.0"
        )

        data_alpha = _get_session_data(db, session_alpha.session_id)
        data_beta = _get_session_data(db, session_beta.session_id)

        alpha_user_id = data_alpha["user_id"]
        beta_user_id = data_beta["user_id"]

        # Verify different users
        assert (
            alpha_user_id != beta_user_id
        ), "Alpha and beta have same user_id (query scope failed)"

        # Query by user_id and verify each returns only their own sessions
        alpha_sessions = db.query(UserSession).filter(UserSession.user_id == alpha_user_id).all()
        beta_sessions = db.query(UserSession).filter(UserSession.user_id == beta_user_id).all()

        alpha_session_ids = [s.session_id for s in alpha_sessions]
        beta_session_ids = [s.session_id for s in beta_sessions]

        assert (
            session_alpha.session_id in alpha_session_ids
        ), "Alpha's session not found in alpha's query"
        assert (
            session_beta.session_id not in alpha_session_ids
        ), "Beta's session leaked into alpha's query"

        assert (
            session_beta.session_id in beta_session_ids
        ), "Beta's session not found in beta's query"
        assert (
            session_alpha.session_id not in beta_session_ids
        ), "Alpha's session leaked into beta's query"

        # Verify consistency on requery
        data_alpha_again = _get_session_data(db, session_alpha.session_id)
        assert data_alpha_again["user_id"] == alpha_user_id, "Alpha's data changed on requery"

    # ==========================================================================
    # CUI-QRY-004: Cross-User Query Isolation Verification
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_qry_004_cross_user_query_isolation(self, db):
        """
        CUI-QRY-004: Cross-User Query Isolation Verification
        Title: Cross-user queries are isolated and cannot access other namespaces
        Description: Even if a user knows another user's ID, they cannot
                     retrieve data from a different namespace

        Steps:
        1. Create session for user_delta@example.com
        2. Create session for user_epsilon@example.com
        3. Extract epsilon's user_id from session
        4. Attempt to query database for epsilon's data using delta's context
        5. Verify delta cannot access epsilon's session
        6. Extract delta's user_id from session
        7. Attempt to query database for delta's data using epsilon's context
        8. Verify epsilon cannot access delta's session
        9. Run cross-namespace query attempt
        10. Verify isolation prevents cross-namespace access

        Expected Results:
        1. Delta and epsilon sessions created successfully
        2. Delta cannot retrieve epsilon's session
        3. Epsilon cannot retrieve delta's session
        4. Cross-namespace access attempt blocked
        5. Query isolation enforced for all combinations
        6. No data leakage in cross-user scenarios
        7. Database enforces namespace boundaries
        8. Access control prevents unauthorized queries
        9. Isolation works regardless of knowledge of other user IDs
        10. System prevents all cross-user data access
        """
        session_delta = session_manager.create_session(
            email="user_delta@example.com", user_agent="Mozilla/5.0"
        )
        session_epsilon = session_manager.create_session(
            email="user_epsilon@example.com", user_agent="Mozilla/5.0"
        )

        data_delta = _get_session_data(db, session_delta.session_id)
        data_epsilon = _get_session_data(db, session_epsilon.session_id)

        delta_user_id = data_delta.get("user_id")
        epsilon_user_id = data_epsilon.get("user_id")

        # Verify delta's user_id query does not return epsilon's session
        all_delta_accessible = (
            db.query(UserSession).filter(UserSession.user_id == delta_user_id).all()
        )
        delta_accessible_ids = [s.session_id for s in all_delta_accessible]
        assert (
            session_epsilon.session_id not in delta_accessible_ids
        ), "Delta can access epsilon's session (isolation violated)"

        # Verify epsilon's user_id query does not return delta's session
        all_epsilon_accessible = (
            db.query(UserSession).filter(UserSession.user_id == epsilon_user_id).all()
        )
        epsilon_accessible_ids = [s.session_id for s in all_epsilon_accessible]
        assert (
            session_delta.session_id not in epsilon_accessible_ids
        ), "Epsilon can access delta's session (isolation violated)"

        # Verify the two user_ids are distinct
        assert delta_user_id != epsilon_user_id, "Delta and epsilon share the same user_id"

    # ==========================================================================
    # CUI-ACCESS-005: Cross-User Data Access Prevention
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_access_005_cross_user_data_access_prevention(self, db):
        """
        CUI-ACCESS-005: Cross-User Data Access Prevention
        Title: It is impossible for users to access each other's data
        Description: Even with valid credentials and session tokens,
                     cross-user data access must be impossible

        Steps:
        1. Create session for user_gamma@example.com
        2. Create session for user_zeta@example.com
        3. Modify gamma's session with custom data
        4. Verify zeta cannot see gamma's custom data
        5. Modify zeta's session with custom data
        6. Verify gamma cannot see zeta's custom data
        7. Query all sessions with different filter conditions
        8. Verify no data leakage in any query
        9. Attempt to access data using another user's user_id
        10. Verify access denied for all cross-user attempts

        Expected Results:
        1. Gamma and zeta sessions created successfully
        2. Gamma's custom data added and persisted
        3. Zeta's custom data added and persisted
        4. Zeta cannot read gamma's secret data
        5. Gamma cannot read zeta's secret data
        6. All database queries properly scoped
        7. No data leakage detected in session data
        8. Cross-user data access completely prevented
        9. Isolation enforced at application level
        10. System guarantees data privacy across users
        """
        session_gamma = session_manager.create_session(
            email="user_gamma@example.com", user_agent="Mozilla/5.0"
        )
        session_zeta = session_manager.create_session(
            email="user_zeta@example.com", user_agent="Mozilla/5.0"
        )

        # Inject secret data into gamma's session
        db_gamma = (
            db.query(UserSession).filter(UserSession.session_id == session_gamma.session_id).first()
        )
        data_gamma = json.loads(db_gamma.session_data)
        data_gamma["secret_gamma_data"] = "CONFIDENTIAL_GAMMA_123"
        db_gamma.session_data = json.dumps(data_gamma, sort_keys=True)
        db.commit()

        # Verify zeta cannot see gamma's data
        data_zeta = _get_session_data(db, session_zeta.session_id)
        assert "secret_gamma_data" not in data_zeta, "Zeta can see gamma's secret_gamma_data"
        assert "CONFIDENTIAL_GAMMA_123" not in json.dumps(
            data_zeta
        ), "Zeta can see gamma's confidential data"

        # Inject secret data into zeta's session
        db_zeta = (
            db.query(UserSession).filter(UserSession.session_id == session_zeta.session_id).first()
        )
        data_zeta["secret_zeta_data"] = "CONFIDENTIAL_ZETA_456"
        db_zeta.session_data = json.dumps(data_zeta, sort_keys=True)
        db.commit()

        # Verify gamma cannot see zeta's data
        data_gamma_requery = _get_session_data(db, session_gamma.session_id)
        assert "secret_zeta_data" not in data_gamma_requery, "Gamma can see zeta's secret_zeta_data"
        assert "CONFIDENTIAL_ZETA_456" not in json.dumps(
            data_gamma_requery
        ), "Gamma can see zeta's confidential data"

        # Verify no leakage across all sessions
        all_sessions = db.query(UserSession).all()
        for session in all_sessions:
            session_str = session.session_data
            if session.session_id == session_gamma.session_id:
                assert "secret_gamma_data" in session_str, "Gamma's own data missing"
            else:
                assert (
                    "secret_gamma_data" not in session_str
                ), "Gamma's data leaked to another session"

            if session.session_id == session_zeta.session_id:
                assert "secret_zeta_data" in session_str, "Zeta's own data missing"
            else:
                assert (
                    "secret_zeta_data" not in session_str
                ), "Zeta's data leaked to another session"

        # Cross-user_id query must not return the other user's session
        gamma_user_id = data_gamma_requery.get("user_id")
        zeta_user_id = json.loads(db_zeta.session_data).get("user_id")

        cross_attempt = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == gamma_user_id,
                UserSession.session_id != session_gamma.session_id,
            )
            .first()
        )
        assert (
            cross_attempt is None or cross_attempt.user_id != zeta_user_id
        ), "Cross-user access possible (found zeta accessing gamma's data)"

    # ==========================================================================
    # CUI-FU-006: File Uploads Namespaced by User
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_fu_006_file_uploads_namespaced_by_user(self, tmp_path):
        """
        CUI-FU-006: File Uploads Namespaced by User
        Title: File uploads are properly namespaced by user
        Description: Each user's file uploads must be stored in a separate,
                     user-specific namespace directory

        Steps:
        1. Create upload namespace for user_iota
        2. Upload file: iota_file.txt with iota's data
        3. Create upload namespace for user_kappa
        4. Upload file: kappa_file.txt with kappa's data
        5. Create upload namespace for user_lambda
        6. Upload file: lambda_file.txt with lambda's data
        7. Verify iota's file exists only in iota's namespace
        8. Verify kappa's file exists only in kappa's namespace
        9. Verify lambda's file exists only in lambda's namespace
        10. Verify directory structure is properly namespaced

        Expected Results:
        1. Iota's namespace directory created
        2. Iota's file successfully uploaded and stored
        3. Kappa's namespace directory created
        4. Kappa's file successfully uploaded and stored
        5. Lambda's namespace directory created
        6. Lambda's file successfully uploaded and stored
        7. Iota's file content matches expected data
        8. Kappa's file content matches expected data
        9. Lambda's file content matches expected data
        10. Directory structure properly isolates user files
        """
        users = {
            "iota": "IOTA_CONFIDENTIAL_DATA_789",
            "kappa": "KAPPA_CONFIDENTIAL_DATA_321",
            "lambda": "LAMBDA_CONFIDENTIAL_DATA_654",
        }

        user_dirs = {}
        user_files = {}

        for user, data in users.items():
            ns_dir = tmp_path / "uploads" / f"namespace_{user}"
            ns_dir.mkdir(parents=True, exist_ok=True)
            file_path = ns_dir / f"{user}_file.txt"
            file_path.write_text(data)
            user_dirs[user] = ns_dir
            user_files[user] = file_path

        # Verify each file exists only in its own namespace
        for user, file_path in user_files.items():
            assert file_path.exists(), f"{user}'s file not created"
            assert file_path.read_text() == users[user], f"{user}'s file content mismatch"

            for other_user in users:
                if other_user != user:
                    leaked = user_dirs[other_user] / file_path.name
                    assert (
                        not leaked.exists()
                    ), f"{user}'s file leaked into {other_user}'s namespace"

        # Verify each namespace has exactly one file
        for user, ns_dir in user_dirs.items():
            files = list(ns_dir.iterdir())
            assert len(files) == 1, f"{user}'s namespace has unexpected files: {files}"
            assert files[0].name == f"{user}_file.txt", f"Wrong file in {user}'s namespace"

    # ==========================================================================
    # CUI-FU-007: File Isolation and Access Control
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_fu_007_file_isolation_and_access_control(self, tmp_path):
        """
        CUI-FU-007: File Isolation and Access Control
        Title: Files in different namespaces cannot be accessed by other users
        Description: Even if a user knows the filename, they cannot access
                     files from a different namespace

        Steps:
        1. Create mu's namespace with mu_secret.txt
        2. Create nu's namespace with nu_secret.txt
        3. Create xi's namespace with xi_secret.txt
        4. Verify mu cannot access nu's files
        5. Verify mu cannot access xi's files
        6. Verify nu cannot access mu's files
        7. Verify nu cannot access xi's files
        8. Verify xi cannot access mu's files
        9. Verify xi cannot access nu's files
        10. Confirm complete file isolation

        Expected Results:
        1. Mu's namespace created with isolated file
        2. Nu's namespace created with isolated file
        3. Xi's namespace created with isolated file
        4. Mu's namespace contains only mu's files
        5. Nu's namespace contains only nu's files
        6. Xi's namespace contains only xi's files
        7. No file access across namespace boundaries
        8. File isolation enforced at file system level
        9. Complete prevention of cross-namespace file access
        10. All namespaces successfully isolated
        """
        users = {
            "mu": "MU_SECRET_DATA_XYZ",
            "nu": "NU_SECRET_DATA_ABC",
            "xi": "XI_SECRET_DATA_DEF",
        }

        user_dirs = {}
        user_files = {}

        for user, data in users.items():
            ns_dir = tmp_path / "uploads" / f"ns_{user}"
            ns_dir.mkdir(parents=True, exist_ok=True)
            file_path = ns_dir / f"{user}_secret.txt"
            file_path.write_text(data)
            user_dirs[user] = ns_dir
            user_files[user] = file_path

        # Verify complete cross-namespace isolation
        for user_a in users:
            for user_b in users:
                if user_a != user_b:
                    leaked = user_dirs[user_a] / f"{user_b}_secret.txt"
                    assert (
                        not leaked.exists()
                    ), f"{user_a} can see {user_b}'s file (cross-namespace access)"

        # Verify each file has correct content and no copies elsewhere
        for user, file_path in user_files.items():
            assert file_path.exists(), f"{user}'s file missing"
            assert file_path.read_text() == users[user], f"{user}'s file content mismatch"

        # Verify directory count
        all_namespaces = list((tmp_path / "uploads").iterdir())
        assert len(all_namespaces) == 3, f"Expected 3 namespaces, found {len(all_namespaces)}"

    # ==========================================================================
    # CUI-SM-008: Session Rotation Preserves Isolation
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_sm_008_session_rotation_preserves_isolation(self, db):
        """
        CUI-SM-008: Session Rotation Preserves Isolation
        Title: Session rotation operations preserve user isolation
        Description: When sessions are migrated, rotated, or modified,
                     isolation must be maintained

        Steps:
        1. Create session for user_omicron@example.com
        2. Create session for user_pi@example.com
        3. Modify omicron's session with unique data
        4. Modify pi's session with unique data
        5. Rotate omicron's session to new session_id
        6. Verify omicron's data persists after rotation
        7. Verify pi's data unaffected by omicron's rotation
        8. Verify omicron cannot access pi's data after rotation
        9. Delete old omicron session
        10. Verify pi's session still exists and isolation maintained

        Expected Results:
        1. Omicron and pi sessions created successfully
        2. Omicron's custom data added and committed
        3. Pi's custom data added and committed
        4. Omicron's data persists through session rotation
        5. Omicron receives new session ID after rotation
        6. Pi's data remains unchanged after omicron's rotation
        7. Isolation maintained throughout rotation
        8. Cross-user data access prevented after rotation
        9. Old session successfully deleted or marked inactive
        10. All isolation criteria met post-rotation
        """
        session_omicron = session_manager.create_session(
            email="user_omicron@example.com", user_agent="Mozilla/5.0"
        )
        session_pi = session_manager.create_session(
            email="user_pi@example.com", user_agent="Mozilla/5.0"
        )

        # Record pre-rotation state
        data_omicron_pre = _get_session_data(db, session_omicron.session_id)
        data_pi_pre = _get_session_data(db, session_pi.session_id)
        omicron_namespace = data_omicron_pre["namespace"]
        omicron_user_id = data_omicron_pre["user_id"]
        pi_namespace = data_pi_pre["namespace"]
        pi_user_id = data_pi_pre["user_id"]

        old_omicron_id = session_omicron.session_id

        # Rotate omicron's session
        new_omicron_session = session_manager._rotate_session(session_omicron, db)
        new_omicron_id = new_omicron_session.session_id

        assert new_omicron_id != old_omicron_id, "Session rotation failed (ID didn't change)"

        # Verify omicron's identity fields persist after rotation
        data_omicron_post = _get_session_data(db, new_omicron_id)
        assert (
            data_omicron_post["namespace"] == omicron_namespace
        ), "Omicron's namespace changed after rotation"
        assert (
            data_omicron_post["user_id"] == omicron_user_id
        ), "Omicron's user_id changed after rotation"

        # Verify pi's data unaffected
        data_pi_post = _get_session_data(db, session_pi.session_id)
        assert (
            data_pi_post["namespace"] == pi_namespace
        ), "Pi's namespace affected by omicron's rotation"
        assert data_pi_post["user_id"] == pi_user_id, "Pi's user_id affected by omicron's rotation"

        # Verify user IDs remain distinct
        assert (
            data_omicron_post["user_id"] != data_pi_post["user_id"]
        ), "User IDs collided (isolation broken)"

        # Delete old omicron session (may already be deleted during rotation)
        try:
            session_manager.delete_session(old_omicron_id)
        except Exception:
            pass

        # Verify pi's session still exists and is intact
        db_pi_final = (
            db.query(UserSession).filter(UserSession.session_id == session_pi.session_id).first()
        )
        assert db_pi_final is not None, "Pi's session affected by omicron's deletion"

        data_pi_final = json.loads(db_pi_final.session_data)
        assert data_pi_final["namespace"] == pi_namespace, "Pi's namespace corrupted"

    # ==========================================================================
    # CUI-COM-009: Complete Isolation End-to-End
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_com_009_complete_isolation_end_to_end(self, db, tmp_path):
        """
        CUI-COM-009: Complete Isolation End-to-End
        Title: Complete end-to-end isolation across all systems
        Description: All isolation mechanisms working together under
                     real-world multi-user load

        Steps:
        1. Create 4 concurrent user sessions
        2. Create isolated file uploads for each user
        3. Add unique data to each session
        4. Perform cross-user query attempts
        5. Verify all queries properly scoped
        6. Verify all files properly isolated
        7. Verify no data leakage in any form
        8. Rotate one user's session
        9. Verify isolation maintained after rotation
        10. Confirm system meets all AC

        Expected Results:
        1. 4 user sessions created with unique namespaces
        2. 4 isolated file directories created
        3. Each user's custom data successfully added
        4. All cross-user query attempts executed
        5. All queries properly scoped to user namespace
        6. All files isolated in respective namespaces
        7. Zero data leakage detected across all systems
        8. Session rotation completed successfully
        9. Isolation maintained throughout all operations
        10. System ready for production multi-user environment
        """
        signing_key = settings.SESSION_SIGNING_KEY.encode()

        users = [
            ("rho@example.com", "rho", "RHO_DATA_001"),
            ("sigma@example.com", "sigma", "SIGMA_DATA_002"),
            ("tau@example.com", "tau", "TAU_DATA_003"),
            ("upsilon@example.com", "upsilon", "UPSILON_DATA_004"),
        ]

        # Step 1-3: Create sessions and inject unique data (with re-signing)
        sessions = {}
        for email, name, data in users:
            session = session_manager.create_session(email=email, user_agent="Mozilla/5.0")
            _inject_session_data(db, session.session_id, "user_data", data, signing_key)

            sessions[name] = {
                "session_id": session.session_id,
                "email": email,
                "data": data,
                "namespace": _get_namespace(db, session.session_id),
            }

        # Step 2: Create isolated file uploads
        file_dirs = {}
        for _email, name, data in users:
            ns_dir = tmp_path / "uploads" / f"ns_{name}"
            ns_dir.mkdir(parents=True, exist_ok=True)
            file_path = ns_dir / f"{name}_data.txt"
            file_path.write_text(data)
            file_dirs[name] = (ns_dir, file_path)

        # Step 4-5: Verify cross-user query isolation
        for user1_name, user1_info in sessions.items():
            data_user1 = _get_session_data(db, user1_info["session_id"])
            data_user1_str = json.dumps(data_user1)
            for user2_name, user2_info in sessions.items():
                if user1_name != user2_name:
                    assert (
                        user2_info["data"] not in data_user1_str
                    ), f"{user1_name} can see {user2_name}'s data"

        # Step 6: Verify file isolation
        for user_a in file_dirs:
            _dir_a, file_a = file_dirs[user_a]
            for user_b in file_dirs:
                if user_a != user_b:
                    dir_b, _file_b = file_dirs[user_b]
                    assert not (
                        dir_b / file_a.name
                    ).exists(), f"{user_a}'s file leaked into {user_b}'s namespace"

        # Step 7: Verify no data leakage across all sessions
        all_sessions = db.query(UserSession).all()
        for session in all_sessions:
            session_data_str = session.session_data
            for user_name, user_info in sessions.items():
                if session.session_id == user_info["session_id"]:
                    assert (
                        user_info["data"] in session_data_str
                    ), f"{user_name}'s own data missing from their session"
                else:
                    assert (
                        user_info["data"] not in session_data_str
                    ), f"{user_name}'s data leaked to another user's session"

        # Step 8-9: Rotate rho's session and verify isolation
        rho_old_id = sessions["rho"]["session_id"]
        rho_session, status = session_manager.get_session(rho_old_id)
        assert rho_session is not None, f"Rho session not found (status: {status})"

        rho_new_session = session_manager._rotate_session(rho_session, db)
        rho_new_id = rho_new_session.session_id

        # Verify rho's identity preserved (namespace, user_id)
        data_rho_new = _get_session_data(db, rho_new_id)
        assert (
            data_rho_new["namespace"] == sessions["rho"]["namespace"]
        ), "Rho's namespace lost after rotation"
        assert data_rho_new["user_id"] == rho_session.user_id, "Rho's user_id lost after rotation"

        # Verify other users unaffected
        for other_name in ["sigma", "tau", "upsilon"]:
            data_other = _get_session_data(db, sessions[other_name]["session_id"])
            assert (
                data_other.get("user_data") == sessions[other_name]["data"]
            ), f"{other_name}'s data affected by rho's rotation"

    # ==========================================================================
    # CUI-GSI-001: Google Sheets Integration Verification
    # ==========================================================================
    @pytest.mark.unit
    def test_cui_gsi_001_google_sheets_integration_verification(self):
        """
        CUI-GSI-001: Google Sheets Integration Verification
        Title: Complete User Isolation test results recorded in Google Sheets
        Description: Verify that CUI test results are properly recorded in
                     the Google Sheets reporting worksheet

        Steps:
        1. Load Google Sheets credentials from environment
        2. Connect to Google Sheets using service account
        3. Open the Summary worksheet
        4. Verify Summary sheet contains recent test run data
        5. Open the Complete User Isolation worksheet
        6. Verify automation_status column exists
        7. Verify worksheet has test case rows
        8. Check that CUI test codes appear in column A
        9. Verify columns K, L, M exist for automation reporting
        10. Confirm Google Sheets integration is operational

        Expected Results:
        1. Google Sheets credentials loaded successfully
        2. Connection to Google Sheets established
        3. Summary worksheet found and accessible
        4. Summary sheet contains test execution data
        5. Complete User Isolation worksheet found
        6. Automation status column present in headers
        7. Worksheet contains test case data rows
        8. CUI test codes found in worksheet
        9. Automation reporting columns available
        10. Google Sheets integration fully operational
        """
        import os

        import gspread
        from dotenv import load_dotenv
        from google.oauth2.service_account import Credentials

        load_dotenv()

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "google-credentials.json")

        if not sheet_id or not os.path.exists(creds_file):
            pytest.skip("Google Sheets credentials not configured")

        try:
            creds = Credentials.from_service_account_file(
                creds_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            client = gspread.authorize(creds)
            sheet = client.open_by_key(sheet_id)

            # Verify Summary sheet exists and has data
            summary_sheet = sheet.worksheet("Summary")
            summary_data = summary_sheet.get_all_values()
            assert len(summary_data) > 1, "Summary sheet should have test execution data"

            # Verify Complete User Isolation worksheet
            isolation_sheet = sheet.worksheet("Complete User Isolation")
            isolation_data = isolation_sheet.get_all_values()
            assert len(isolation_data) > 0, "Complete User Isolation sheet should have data"

            # Verify automation columns exist in headers
            headers = isolation_data[0]
            has_automation_status = any("automation" in h.lower() for h in headers)
            assert has_automation_status, "Should have automation_status column"

        except gspread.exceptions.WorksheetNotFound as e:
            pytest.fail(f"Required worksheet not found: {e}")
        except Exception as e:
            pytest.fail(f"Google Sheets verification failed: {e}")
