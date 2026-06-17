from sqlalchemy import Column,Integer,String
from database import Base
from sqlalchemy.orm import relationship

class Brands(Base):
    __tablename__="brands"
    id=Column(Integer,primary_key=True)
    name_brand=Column(String(200),nullable=False)
    slug=Column(String(100),nullable=False)
    logo_url=Column(String(255),nullable=False)
    website_url=Column(String(255),nullable=False)
    models=relationship("Models",back_populates='brand')