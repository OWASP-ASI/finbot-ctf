"""FinDrive repositories -- data access for stored files."""

from datetime import UTC, datetime

from finbot.core.data.repositories import NamespacedRepository
from finbot.mcp.servers.findrive.models import FinDriveFile


class FinDriveFileRepository(NamespacedRepository):
    """Repository for FinDriveFile -- mock Google Drive file storage."""

    def create_file(
        self,
        filename: str,
        content_text: str,
        vendor_id: int | None = None,
        content_type: str = "text/plain",
        file_type: str = "pdf",
        folder_path: str = "/",
    ) -> FinDriveFile:
        f = FinDriveFile(
            namespace=self.namespace,
            vendor_id=vendor_id,
            filename=filename,
            content_text=content_text,
            content_type=content_type,
            file_type=file_type,
            file_size=len(content_text.encode("utf-8")),
            folder_path=folder_path,
        )
        self.db.add(f)
        self.db.commit()
        self.db.refresh(f)
        return f

    def get_file(self, file_id: int) -> FinDriveFile | None:
        return (
            self._add_namespace_filter(self.db.query(FinDriveFile), FinDriveFile)
            .filter(FinDriveFile.id == file_id)
            .first()
        )

    def list_files(
        self,
        vendor_id: int | None = None,
        folder_path: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FinDriveFile]:
        query = self._add_namespace_filter(self.db.query(FinDriveFile), FinDriveFile)
        if vendor_id is not None:
            query = query.filter(FinDriveFile.vendor_id == vendor_id)
        if folder_path is not None:
            query = query.filter(FinDriveFile.folder_path == folder_path)
        return query.order_by(FinDriveFile.created_at.desc()).offset(offset).limit(limit).all()

    def search_files(self, query_str: str, limit: int = 20) -> list[FinDriveFile]:
        return (
            self._add_namespace_filter(self.db.query(FinDriveFile), FinDriveFile)
            .filter(
                FinDriveFile.filename.ilike(f"%{query_str}%")
                | FinDriveFile.content_text.ilike(f"%{query_str}%")
            )
            .order_by(FinDriveFile.created_at.desc())
            .limit(limit)
            .all()
        )

    def delete_file(self, file_id: int) -> bool:
        f = self.get_file(file_id)
        if f:
            self.db.delete(f)
            self.db.commit()
            return True
        return False

    def update_file(
        self, file_id: int, filename: str | None = None, content_text: str | None = None
    ) -> FinDriveFile | None:
        f = self.get_file(file_id)
        if not f:
            return None
        if filename is not None:
            f.filename = filename
        if content_text is not None:
            f.content_text = content_text
            f.file_size = len(content_text.encode("utf-8"))
        f.updated_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(f)
        return f

    def get_file_count(self, vendor_id: int | None = None) -> int:
        query = self._add_namespace_filter(self.db.query(FinDriveFile), FinDriveFile)
        if vendor_id is not None:
            query = query.filter(FinDriveFile.vendor_id == vendor_id)
        return query.count()
