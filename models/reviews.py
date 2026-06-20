from sqlalchemy import Integer,Column,String,Text,Boolean,DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class Reviews(Base):
    __tablename__="reviews"

    id=Column(Integer,primary_key=True)
    model_id=Column(Integer,ForeignKey("models.id"))
    user_id=Column(Integer,ForeignKey("users.id"))
    
    rating=Column(Integer,nullable=False)
    body=Column(Text,nullable=True)#текст отзыва
    is_approved=Column(Boolean,default=False)#выложен отзыв или нет
    created_at=Column(DateTime, server_default=func.now(), nullable=False)

    model=relationship("Models",back_populates="reviews")
    user=relationship("Users",back_populates="reviews")
    likes=relationship("ReviewsLikes",back_populates="review")