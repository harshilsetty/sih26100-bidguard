from sqlalchemy import Column, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.core.database import Base
from app.core.config import settings
from app.models.base import BaseModelMixin


class DocumentChunk(Base, BaseModelMixin):
    __tablename__ = "document_chunks"

    bid_document_id = Column(UUID(as_uuid=True), ForeignKey("bid_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    bidder_id = Column(UUID(as_uuid=True), ForeignKey("bidders.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, index=True)
    chunk_index = Column(Integer, default=0, nullable=False)
    start_char = Column(Integer, nullable=True)
    end_char = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    # Configurable vector embedding dimension matching verified model
    embedding = Column(Vector(dim=settings.EMBEDDING_DIM), nullable=True)

    # Relationships
    document = relationship("BidDocument", back_populates="chunks")
    bidder = relationship("Bidder", back_populates="chunks")
