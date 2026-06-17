from sqlalchemy import Integer,String,Column,Text,Boolean,DateTime,ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class News(Base):
    __tablename__="news"

    id=Column(Integer, primary_key=True)
    source_id=Column(Integer,ForeignKey('news_source.id'))
    title=Column(String(255),nullable=False)#оригинальный заголовок
    title_deepseek=Column(String(255),nullable=False)
    content_original=Column(Text,nullable=False)
    content_deepseek=Column(Text,nullable=False)
    source_url=Column(String(255),nullable=False)
    image_url=Column(String(255))
    is_published=Column(Boolean,default=False)
    published_at=Column(DateTime,nullable=False)
    created_at=Column(DateTime,server_default=func.now(),nullable=False)
    source=relationship("NewSource",back_populates="news")
    tag_links=relationship("NewToTags",back_populates="news")