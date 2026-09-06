from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.models.base import BaseModelMixin


class DocumentChunk(Base, BaseModelMixin):
    __tablename__ = "document_chunks"

    bid_document_id = Column(UUID(as_uuid=True), ForeignKey("bid_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # 4096-dimensional or flexible vector embedding
    embedding = Column(Vector(dim=4096), nullable=True)

    # Relationships
    document = relationship("BidDocument", back_populates="chunks")
