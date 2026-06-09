"""FinDrive data models -- file storage for invoice documents."""

from datetime import UTC, datetime

from sqlalchemy import Column
from sqlalchemy import DateTime as _DateTime
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from finbot.core.data.database import Base

DateTime = _DateTime(timezone=True)


class FinDriveFile(Base):
    """Files stored in the FinDrive mock Google Drive.
    In CTF, these files are the indirect prompt injection delivery mechanism --
    poisoned content in uploaded "invoice documents" enters the LLM context
    when agents read them.
    """

    __tablename__ = "findrive_files"

    id = Column[int](Integer, primary_key=True, autoincrement=True)
    namespace = Column[str](String(64), nullable=False, index=True)
    vendor_id = Column[int](Integer, ForeignKey("vendors.id"), nullable=True)

    filename = Column[str](String(255), nullable=False)
    content_text = Column[str](Text, nullable=False)
    content_type = Column[str](String(50), nullable=False, default="text/plain")
    file_type = Column[str](String(20), nullable=False, default="pdf")
    file_size = Column[int](Integer, nullable=False, default=0)
    folder_path = Column[str](String(500), nullable=False, default="/")

    created_at = Column[datetime](DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column[datetime](
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    vendor = relationship("Vendor", foreign_keys=[vendor_id])

    __table_args__ = (
        Index("idx_fdf_namespace", "namespace"),
        Index("idx_fdf_namespace_vendor", "namespace", "vendor_id"),
        Index("idx_fdf_namespace_folder", "namespace", "folder_path"),
    )

    def __repr__(self) -> str:
        return f"<FinDriveFile(id={self.id}, filename='{self.filename}', namespace='{self.namespace}')>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "vendor_id": self.vendor_id,
            "filename": self.filename,
            "content_type": self.content_type,
            "file_type": self.file_type,
            "file_size": self.file_size,
            "folder_path": self.folder_path,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }

    def to_dict_with_content(self) -> dict:
        result = self.to_dict()
        result["content_text"] = self.content_text
        return result
