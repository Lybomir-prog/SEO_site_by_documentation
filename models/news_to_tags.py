from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from database import Base


class NewsToTags(Base):
    __tablename__ = "news_to_tags"

    id = Column(Integer, primary_key=True)
    news_id = Column(Integer, ForeignKey("news.id"), nullable=False)
    tag_id = Column(Integer, ForeignKey("news_tags.id"), nullable=False)

    news = relationship("News", back_populates="tag_links")
    tag = relationship("NewsTags", back_populates="news_links")
