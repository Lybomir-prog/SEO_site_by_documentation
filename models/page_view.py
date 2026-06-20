from sqlalchemy import Column,Integer,String,DateTime,Enum
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class PageView(Base):
    __tablename__='page_view'

    id=Column(Integer,primary_key=True)
    path=Column(String(255),nullable=False)#путь который открыли по ссылке 
    fingerprint=Column(String(500),nullable=False)
    user_agent=Column(String(255),nullable=False)#user-agent браузер
    country=Column(String(100),nullable=False)
    city=Column(String(100),nullable=False)
    created_at=Column(DateTime,server_default=func.now(),nullable=False)
    
    