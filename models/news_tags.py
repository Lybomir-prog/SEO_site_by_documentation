from sqlalchemy import Integer,Column,String
from sqlalchemy.orm import relationship
from database import Base

class NewsTags(Base):
    __tablename__="news_tags"

    id=Column(Integer,primary_key=True)
    name=Column(String(100),nullable=False)
    slug=Column(String(255),nullable=False)
    
    new_links=relationship("NewsToTags",back_populates="tag")
