"""
Unit tests for finbot/mcp/servers/findrive/repositories.py

Covers uncovered branches in FinDriveFileRepository:
- delete_file returns False when file not found (line 88)
- update_file — full method including not-found, filename-only, content-only, both (lines 93-104)
- get_file_count — with and without vendor_id filter (lines 107-112)

Also covers isolation and pagination edge cases:
- list_files vendor_id and folder_path filters
- list_files pagination (limit/offset)
- cross-namespace isolation via get_file

All tests use in-memory SQLite via the shared db fixture.
"""

import pytest

from finbot.core.auth.session import session_manager
from finbot.core.data.repositories import VendorRepository
from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


# ============================================================================
# Helpers
# ============================================================================

def make_repo(db, session):
    return FinDriveFileRepository(db, session)


def make_vendor(db, session, email="vendor@test.com", company_name="Test Vendor"):
    repo = VendorRepository(db, session)
    return repo.create_vendor(
        company_name=company_name,
        vendor_category="Technology",
        industry="Software",
        services="Consulting",
        contact_name="Alice",
        email=email,
        tin="12-3456789",
        bank_account_number="123456789012",
        bank_name="Test Bank",
        bank_routing_number="021000021",
        bank_account_holder_name="Alice",
    )


def create_file(repo, filename="test.pdf", content="Hello", folder="/", vendor_id=None):
    return repo.create_file(
        filename=filename,
        content_text=content,
        folder_path=folder,
        vendor_id=vendor_id,
    )


# ============================================================================
# delete_file — not-found branch
# ============================================================================

class TestDeleteFile:

    def test_fd_repo_001_delete_file_returns_true_when_found(self, db):
        """
        FD-REPO-001

        Title: delete_file returns True when the file exists and is deleted
        Basically question: Does delete_file return True and remove the file when it exists?

        Steps:
            1. Create a file.
            2. Call delete_file with the file's id.
        Expected Results:
            Returns True; subsequent get_file returns None.
        """
        session = session_manager.create_session(email="fd_repo_001@test.com")
        repo = make_repo(db, session)
        f = create_file(repo)

        result = repo.delete_file(f.id)

        assert result is True
        assert repo.get_file(f.id) is None

    def test_fd_repo_002_delete_file_returns_false_when_not_found(self, db):
        """
        FD-REPO-002

        Title: delete_file returns False when the file does not exist
        Basically question: Does delete_file return False gracefully for a non-existent file_id?

        Steps:
            1. Call delete_file with file_id=99999.
        Expected Results:
            Returns False without raising.
        """
        session = session_manager.create_session(email="fd_repo_002@test.com")
        repo = make_repo(db, session)

        result = repo.delete_file(99999)

        assert result is False


# ============================================================================
# update_file
# ============================================================================

class TestUpdateFile:

    def test_fd_repo_003_update_file_returns_none_when_not_found(self, db):
        """
        FD-REPO-003

        Title: update_file returns None for a non-existent file_id
        Basically question: Does update_file return None gracefully when the file does not exist?

        Steps:
            1. Call update_file with file_id=99999.
        Expected Results:
            Returns None without raising.
        """
        session = session_manager.create_session(email="fd_repo_003@test.com")
        repo = make_repo(db, session)

        result = repo.update_file(99999, filename="new.pdf")

        assert result is None

    def test_fd_repo_004_update_file_updates_filename(self, db):
        """
        FD-REPO-004

        Title: update_file updates the filename when only filename is provided
        Basically question: Does update_file correctly change the filename while leaving content unchanged?

        Steps:
            1. Create a file with filename="old.pdf".
            2. Call update_file with filename="new.pdf".
        Expected Results:
            Returns the file with filename="new.pdf"; content unchanged.
        """
        session = session_manager.create_session(email="fd_repo_004@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, filename="old.pdf", content="Original content")

        result = repo.update_file(f.id, filename="new.pdf")

        assert result is not None
        assert result.filename == "new.pdf"
        assert result.content_text == "Original content"

    def test_fd_repo_005_update_file_updates_content_and_file_size(self, db):
        """
        FD-REPO-005

        Title: update_file updates content_text and recalculates file_size
        Basically question: Does update_file correctly update content_text and update file_size accordingly?

        Steps:
            1. Create a file with short content.
            2. Call update_file with longer content_text.
        Expected Results:
            Returns the file with updated content_text and file_size matching the new content's byte length.
        """
        session = session_manager.create_session(email="fd_repo_005@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, content="Hi")

        new_content = "Much longer content here"
        result = repo.update_file(f.id, content_text=new_content)

        assert result is not None
        assert result.content_text == new_content
        assert result.file_size == len(new_content.encode("utf-8"))

    def test_fd_repo_006_update_file_updates_both_filename_and_content(self, db):
        """
        FD-REPO-006

        Title: update_file updates both filename and content_text when both are provided
        Basically question: Does update_file handle updating both fields simultaneously?

        Steps:
            1. Create a file.
            2. Call update_file with both filename and content_text.
        Expected Results:
            Both fields are updated in the returned file.
        """
        session = session_manager.create_session(email="fd_repo_006@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, filename="original.pdf", content="Old")

        result = repo.update_file(f.id, filename="updated.pdf", content_text="New content")

        assert result.filename == "updated.pdf"
        assert result.content_text == "New content"

    def test_fd_repo_007_update_file_persists_to_db(self, db):
        """
        FD-REPO-007

        Title: update_file changes are durable — re-fetch reflects updates
        Basically question: Does update_file commit changes so a subsequent get_file returns updated data?

        Steps:
            1. Create a file.
            2. Call update_file with a new filename.
            3. Re-fetch via get_file.
        Expected Results:
            Re-fetched file has the updated filename.
        """
        session = session_manager.create_session(email="fd_repo_007@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, filename="before.pdf")

        repo.update_file(f.id, filename="after.pdf")
        fetched = repo.get_file(f.id)

        assert fetched.filename == "after.pdf"


# ============================================================================
# get_file_count
# ============================================================================

class TestGetFileCount:

    def test_fd_repo_008_get_file_count_returns_total(self, db):
        """
        FD-REPO-008

        Title: get_file_count returns total file count with no vendor filter
        Basically question: Does get_file_count return the correct total number of files when no vendor_id is given?

        Steps:
            1. Create 3 files with no vendor_id.
            2. Call get_file_count with no arguments.
        Expected Results:
            Returns 3.
        """
        session = session_manager.create_session(email="fd_repo_008@test.com")
        repo = make_repo(db, session)

        for i in range(3):
            create_file(repo, filename=f"file_{i}.pdf")

        count = repo.get_file_count()

        assert count == 3

    def test_fd_repo_009_get_file_count_filtered_by_vendor_id(self, db):
        """
        FD-REPO-009

        Title: get_file_count filters correctly by vendor_id
        Basically question: Does get_file_count return only the count for a specific vendor when vendor_id is provided?

        Steps:
            1. Create two vendors; create 2 files for vendor_a and 1 file for vendor_b.
            2. Call get_file_count(vendor_id=vendor_a.id).
        Expected Results:
            Returns 2.
        """
        session = session_manager.create_session(email="fd_repo_009@test.com")
        vendor_a = make_vendor(db, session, email="fd_a_009@test.com", company_name="Vendor A 009")
        vendor_b = make_vendor(db, session, email="fd_b_009@test.com", company_name="Vendor B 009")
        repo = make_repo(db, session)

        create_file(repo, filename="a.pdf", vendor_id=vendor_a.id)
        create_file(repo, filename="b.pdf", vendor_id=vendor_a.id)
        create_file(repo, filename="c.pdf", vendor_id=vendor_b.id)

        count = repo.get_file_count(vendor_id=vendor_a.id)

        assert count == 2

    def test_fd_repo_010_get_file_count_returns_zero_when_empty(self, db):
        """
        FD-REPO-010

        Title: get_file_count returns 0 when no files exist
        Basically question: Does get_file_count return 0 for an empty namespace?

        Steps:
            1. No files created.
            2. Call get_file_count.
        Expected Results:
            Returns 0.
        """
        session = session_manager.create_session(email="fd_repo_010@test.com")
        repo = make_repo(db, session)

        count = repo.get_file_count()

        assert count == 0


# ============================================================================
# list_files — filters and pagination
# ============================================================================

class TestListFiles:

    def test_fd_repo_011_list_files_filter_by_folder_path(self, db):
        """
        FD-REPO-011

        Title: list_files filters correctly by folder_path
        Basically question: Does list_files return only files in the specified folder?

        Steps:
            1. Create files in two different folders.
            2. Call list_files with folder_path="/invoices".
        Expected Results:
            Only files in /invoices are returned.
        """
        session = session_manager.create_session(email="fd_repo_011@test.com")
        repo = make_repo(db, session)

        create_file(repo, filename="a.pdf", folder="/invoices")
        create_file(repo, filename="b.pdf", folder="/invoices")
        create_file(repo, filename="c.pdf", folder="/contracts")

        results = repo.list_files(folder_path="/invoices")

        assert len(results) == 2
        assert all(f.folder_path == "/invoices" for f in results)

    def test_fd_repo_012_list_files_respects_limit(self, db):
        """
        FD-REPO-012

        Title: list_files respects the limit parameter
        Basically question: Does list_files return at most limit files?

        Steps:
            1. Create 5 files.
            2. Call list_files with limit=2.
        Expected Results:
            Exactly 2 files returned.
        """
        session = session_manager.create_session(email="fd_repo_012@test.com")
        repo = make_repo(db, session)

        for i in range(5):
            create_file(repo, filename=f"file_{i}.pdf")

        results = repo.list_files(limit=2)

        assert len(results) == 2

    def test_fd_repo_013_get_file_cross_namespace_returns_none(self, db):
        """
        FD-REPO-013

        Title: get_file returns None for a file belonging to a different namespace
        Basically question: Does the namespace filter prevent cross-namespace file access?

        Steps:
            1. Create a file under namespace_a.
            2. Call get_file from a repo scoped to namespace_b.
        Expected Results:
            Returns None.
        """
        session_a = session_manager.create_session(email="fd_repo_013a@test.com")
        session_b = session_manager.create_session(email="fd_repo_013b@test.com")
        repo_a = make_repo(db, session_a)
        repo_b = make_repo(db, session_b)

        f = create_file(repo_a, filename="secret.pdf")

        result = repo_b.get_file(f.id)

        assert result is None


# ============================================================================
# FinDriveFile model methods
# ============================================================================

class TestFinDriveFileModel:

    def test_fd_repo_014_repr(self, db):
        """
        FD-REPO-014

        Title: FinDriveFile __repr__ returns expected string
        Basically question: Does FinDriveFile.__repr__ include the id, filename, and namespace?

        Steps:
            1. Create a file.
            2. Call repr() on it.
        Expected Results:
            String contains the file id, filename, and namespace.
        """
        session = session_manager.create_session(email="fd_repo_014@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, filename="report.pdf")

        r = repr(f)

        assert "report.pdf" in r
        assert str(f.id) in r

    def test_fd_repo_015_to_dict_with_content_includes_content_text(self, db):
        """
        FD-REPO-015

        Title: to_dict_with_content includes content_text field
        Basically question: Does to_dict_with_content return the base dict plus content_text?

        Steps:
            1. Create a file with known content.
            2. Call to_dict_with_content().
        Expected Results:
            Returned dict includes content_text equal to the original content.
        """
        session = session_manager.create_session(email="fd_repo_015@test.com")
        repo = make_repo(db, session)
        f = create_file(repo, content="The quick brown fox")

        result = f.to_dict_with_content()

        assert result["content_text"] == "The quick brown fox"
        assert "id" in result
        assert "filename" in result
