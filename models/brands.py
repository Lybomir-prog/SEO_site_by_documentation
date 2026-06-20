from sqlalchemy import Column,Integer,String,Boolean
from database import Base
from sqlalchemy.orm import relationship

class Brands(Base):
    __tablename__="brands"

    id=Column(Integer,primary_key=True)
    name_brand=Column(String(200),nullable=False)
    slug=Column(String(100),nullable=False)
    logo_url=Column(String(255),nullable=True)
    website_url=Column(String(255),nullable=False)
    docs_url=Column(String(255),nullable=True)#откуда берем документацию
    is_active=Column(Boolean,default=True)

    models=relationship("Models",back_populates='brand')