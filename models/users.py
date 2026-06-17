from sqlalchemy import Column,Integer,String,DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import  func
from database import Base


class Users(Base):
    __tablename__="users"
    id=Column(Integer,primary_key=True)
    name=Column(String(100),nullable=False)
    login=Column(String(100), unique=True, nullable=False)
    email=Column(String(100), unique=True, nullable=False)
    password_hash=Column(String(255),nullable=False)
    last_login_at=Column(DateTime,nullable=False)
    created_at=Column(DateTime, server_default=func.now(), nullable=False)
    reviews=relationship("Reviews", back_populates="user")
    review_likes=relationship("ReviewsLikes",back_populates="user")
