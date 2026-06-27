from sqlalchemy import Column, Integer, String, ForeignKey, Text, DateTime, Boolean
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func


class Models(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("equipment_category.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=True)
    description = Column(Text, nullable=False)  # описание deepseek
    spec = Column(Text, nullable=True)  # json характеристика
    name_equipment = Column(String(255), nullable=False)  # название модели
    slug = Column(String(100), nullable=False)
    image_url = Column(String(255), nullable=True)
    created_at = Column(
        DateTime, server_default=func.now(), nullable=False
    )  # поставь текущее время автоматически
    is_active = Column(Boolean, default=True)

    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(String(500), nullable=True)
    faq_json = Column(Text, nullable=True)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)

    category = relationship("EquipmentCategory", back_populates="models")
    brand = relationship("Brands", back_populates="models")
    documents = relationship("Document", back_populates="model")
    reviews = relationship(
        "Reviews", back_populates="model"
    )  # задаем связь между классов Reviews в данными из Models
