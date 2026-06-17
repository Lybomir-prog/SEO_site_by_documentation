from sqlalchemy import Column,Integer,String,DateTime
from database import Base
from sqlalchemy.orm import relationship

class EquipmentCategory(Base):
    __tablename__="equipment_category"

    id=Column(Integer,primary_key=True)
    name_category=Column(String(255),nullable=False)
    slug=Column(String(255),nullable=False)
    icon=Column(String(255),nullable=False)
    models=relationship("Models",back_populates="category")