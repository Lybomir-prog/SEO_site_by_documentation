from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from database import Base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func


class EquipmentCategory(Base):
    __tablename__ = "equipment_category"

    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey("equipment_category.id"), nullable=True)
    name_category = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False, unique=True)
    icon = Column(String(255), nullable=True)

    # SEO
    meta_description = Column(String(500), nullable=True)
    seo_text = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)
    is_active = Column(Boolean, default=True)

    models = relationship("Models", back_populates="category")
    children = relationship("EquipmentCategory", back_populates="parent")
    parent = relationship(
        "EquipmentCategory", back_populates="children", remote_side=[id]
    )
