from sqlalchemy import Column, Integer, ForeignKey, Text, String, Boolean, DateTime
from database import Base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class Document(Base):
    __tablename__ = "document"

    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)

    title = Column(String(255), nullable=False)  # название документа
    doc_type = Column(
        String(50), nullable=True
    )  # тип документа(документация, инструкция и тд)
    source_url = Column(
        String(500), unique=True, nullable=True
    )  # источник, где нашли страницу

    parser_source = Column(String(100), nullable=True)  # источник парсинга
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    model = relationship("Models", back_populates="documents")
    downloads = relationship("DocumentDownloads", back_populates="document")
    versions = relationship(
        "DocumentVersion", back_populates="document", cascade="all, delete-orphan"
    )
