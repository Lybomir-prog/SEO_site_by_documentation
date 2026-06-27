from sqlalchemy import Integer, String, Column, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("news_source.id"))

    title = Column(String(255), nullable=False)  # оригинальный заголовок
    title_deepseek = Column(String(255), nullable=False)  # заголовок от дипсика
    content_original = Column(Text, nullable=False)  # оригинальный текст новости
    content_deepseek = Column(Text, nullable=False)  # текст от дипсика
    source_url = Column(String(255), nullable=False)  # ссылка на оригинальную новость
    image_url = Column(String(255))
    is_published = Column(Boolean, default=False)
    published_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # SEO
    slug = Column(String(255), nullable=True, unique=True)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    source = relationship("NewsSource", back_populates="news")
    tag_links = relationship("NewsToTags", back_populates="news")
