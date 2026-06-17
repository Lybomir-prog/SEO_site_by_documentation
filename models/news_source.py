from sqlalchemy import Column,Integer,String,DateTime, Enum,Boolean
from sqlalchemy.orm import relationship
from database import Base

class NewsSource(Base):
    __tablename__="news_source"

    id=Column(Integer,primary_key=True)
    name=Column(String(100),nullable=False)
    url=Column(String(255),nullable=False)
    parser_type=Column(Enum("rss","html",name="parser_type_enum"),nullable=False)
    selector=Column(String(500),nullable=False)
    is_active=Column(Boolean,default=False)
    last_parsed=Column(DateTime,nullable=False)
    news=relationship("News",back_populates='source')
    