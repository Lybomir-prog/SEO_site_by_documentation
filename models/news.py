from sqlalchemy import (
    Integer,
    String,
    Column,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(Integer, ForeignKey("news_source.id"), nullable=True)

    # Источник (дублируем строкой — удобно когда source_id не заполнен)
    parser_source = Column(String(50), nullable=True)  # "secnews_rss"

    # Тип контента
    content_type = Column(
        Enum("news", "update", "insight", name="news_content_type_enum"),
        nullable=False,
        default="news",
    )
    news_type = Column(
        Enum(
            "new_model",
            "certificate",
            "compatibility",
            "general",
            name="news_type_enum",
        ),
        nullable=False,
        default="general",
    )

    # Оригинальный контент
    title = Column(String(500), nullable=False)
    content_original = Column(
        Text, nullable=True
    )  # nullable — сохраним даже без текста
    summary = Column(Text, nullable=True)  # краткое описание из RSS

    # Контент от DeepSeek (nullable — заполняется позже)
    title_deepseek = Column(String(500), nullable=True)
    content_deepseek = Column(Text, nullable=True)

    # Ссылки
    source_url = Column(String(1000), nullable=False, unique=True)
    url_hash = Column(
        String(32), nullable=False, unique=True, index=True
    )  # MD5(source_url)

    # Хеш контента для отслеживания изменений
    content_hash = Column(String(32), nullable=True)

    # Фото
    image_url = Column(String(1000), nullable=True)  # og:image оригинал
    image_local_path = Column(String(500), nullable=True)  # локальный путь
    image_downloaded = Column(Boolean, default=False, nullable=False)

    # Привязка к бренду
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)

    # SEO
    slug = Column(String(255), nullable=True, unique=True)

    # Статус публикации
    is_published = Column(Boolean, default=False, nullable=False)
    published_at = Column(DateTime, nullable=True)  # когда опубликовали у нас

    # Дата публикации у источника
    source_published_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    # Relationships
    source = relationship("NewsSource", back_populates="news")
    tag_links = relationship("NewsToTags", back_populates="news")

    # Индексы для быстрых выборок на сайте
    __table_args__ = (
        Index("ix_news_published", "is_published"),
        Index("ix_news_source_date", "source_published_at"),
        Index("ix_news_content_type", "content_type"),
        Index("ix_news_news_type", "news_type"),
    )
