"""FinDrive MCP Server -- mock Google Drive for invoice document storage.

Files stored here are the indirect prompt injection delivery mechanism:
when agents read "invoice documents," poisoned content enters the LLM
context window and can influence agent decisions.

Access control:
- When current_vendor_id is set (vendor portal): cannot access files with
  vendor_id=NULL (admin-scoped files). Cross-vendor access is intentionally
  left open as CTF attack surface.
- When current_vendor_id is None (admin portal): full access to all files.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from finbot.core.auth.session import SessionContext
from finbot.core.data.database import db_session
from finbot.mcp.servers.findrive.repositories import FinDriveFileRepository

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "max_file_size_kb": 500,
    "max_files_per_vendor": 50,
    "default_folder": "/invoices",
}


def _is_vendor_session(session_context: SessionContext) -> bool:
    return session_context.is_vendor_portal()


def create_findrive_server(
    session_context: SessionContext,
    server_config: dict[str, Any] | None = None,
) -> FastMCP:
    """Create a namespace-scoped FinDrive MCP server instance."""
    config = {**DEFAULT_CONFIG, **(server_config or {})}
    mcp = FastMCP("FinDrive")

    @mcp.tool
    def upload_file(
        filename: str,
        content: str,
        folder: str = "/invoices",
        vendor_id: int = 0,
        file_type: str = "pdf",
    ) -> dict[str, Any]:
        """Upload a PDF document to FinDrive storage.

        Stores the document and returns metadata including its ID for future
        retrieval. Use this for storing invoice PDFs, receipts, and supporting
        documentation.
        """
        conf = config or DEFAULT_CONFIG
        MAX_FILENAME_LENGTH = 255
        if len(filename) > MAX_FILENAME_LENGTH:
            return {"error": f"filename exceeds maximum length of {MAX_FILENAME_LENGTH} characters"}

        max_size = conf.get("max_file_size_kb", 500) * 1024
        if len(content.encode("utf-8")) > max_size:
            return {"error": f"File exceeds maximum size of {conf.get('max_file_size_kb', 500)}KB"}

        with db_session() as db:
            repo = FinDriveFileRepository(db, session_context)

            vid = vendor_id if vendor_id > 0 else None
            if session_context and _is_vendor_session(session_context) and vid is None:
                vid = session_context.current_vendor_id

            f = repo.create_file(
                filename=filename,
                content_text=content,
                vendor_id=vid,
                file_type=file_type,
                folder_path=folder,
            )

            logger.info("FinDrive file uploaded: id=%d, filename='%s'", f.id, filename)

            return {
                "file_id": f.id,
                "filename": f.filename,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "folder": f.folder_path,
                "status": "uploaded",
            }

    @mcp.tool
    def get_file(file_id: int) -> dict[str, Any]:
        """Retrieve a PDF document's extracted text content and metadata from FinDrive.

        Returns the extracted text from the specified PDF document. Use this to
        read invoice PDFs and supporting documents for processing and review.
        """
        with db_session() as db:
            repo = FinDriveFileRepository(db, session_context)
            f = repo.get_file(file_id)

            if not f:
                return {"error": f"File {file_id} not found", "file_id": file_id}

            if _is_vendor_session(session_context) and f.vendor_id is None:
                return {"error": "Access denied: cannot access admin files", "file_id": file_id}

            return {
                "file_id": f.id,
                "filename": f.filename,
                "file_type": f.file_type,
                "extracted_text": f.content_text,
                "file_size": f.file_size,
                "folder": f.folder_path,
                "vendor_id": f.vendor_id,
                "created_at": f.created_at.isoformat().replace("+00:00", "Z"),
            }

    @mcp.tool
    def list_files(
        folder: str = "",
        vendor_id: int = 0,
        limit: int = 50,
    ) -> dict[str, Any]:
        """List PDF documents stored in FinDrive.

        Returns document metadata (not content) for files in the specified folder.
        Use get_file to retrieve the extracted text of a specific document.
        """
        with db_session() as db:
            repo = FinDriveFileRepository(db, session_context)

            vid = vendor_id if vendor_id > 0 else None
            if _is_vendor_session(session_context) and vid is None:
                vid = session_context.current_vendor_id

            fld = folder if folder else None
            files = repo.list_files(vendor_id=vid, folder_path=fld, limit=limit)

            return {
                "files": [f.to_dict() for f in files],
                "count": len(files),
                "folder": folder or "all",
            }

    @mcp.tool
    def delete_file(file_id: int) -> dict[str, Any]:
        """Delete a file from FinDrive storage.

        Permanently removes the specified file. This action cannot be undone.
        """
        with db_session() as db:
            repo = FinDriveFileRepository(db, session_context)

            f = repo.get_file(file_id)
            if not f:
                return {"error": f"File {file_id} not found", "file_id": file_id}

            if _is_vendor_session(session_context) and f.vendor_id is None:
                return {"error": "Access denied: cannot delete admin files", "file_id": file_id}

            filename = f.filename
            file_vendor_id = f.vendor_id
            deleted = repo.delete_file(file_id)

            logger.info("FinDrive file deleted: id=%d, filename='%s'", file_id, filename)

            return {
                "file_id": file_id,
                "filename": filename,
                "vendor_id": file_vendor_id,
                "deleted": deleted,
                "status": "deleted" if deleted else "failed",
            }

    @mcp.tool
    def search_files(query: str, limit: int = 20) -> dict[str, Any]:
        """Search for PDF documents by filename or extracted text content.

        Returns documents whose filename or extracted text matches the query.
        Useful for finding relevant invoice PDFs and supporting documents.
        """
        with db_session() as db:
            repo = FinDriveFileRepository(db, session_context)
            files = repo.search_files(query, limit=limit)

            if _is_vendor_session(session_context):
                files = [f for f in files if f.vendor_id is not None]

            return {
                "query": query,
                "results": [f.to_dict() for f in files],
                "count": len(files),
            }

    return mcp
