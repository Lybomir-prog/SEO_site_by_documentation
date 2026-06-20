from sqlalchemy import Column,Integer,DateTime,ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class ReviewsLikes(Base):
    __tablename__="reviews_likes"

    id=Column(Integer,primary_key=True)
    review_id=Column(Integer,ForeignKey("reviews.id"),nullable=False)
    user_id=Column(Integer,ForeignKey("users.id"),nullable=False)

    created_at=Column(DateTime, server_default=func.now(), nullable=False)
    
    review=relationship("Reviews",back_populates="likes")
    user=relationship("Users",back_populates="review_likes")