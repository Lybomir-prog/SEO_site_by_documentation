from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from database import Base
from sqlalchemy.sql import func


class SitePage(Base):
    __tablename__ = "site_pages"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, nullable=False)  # "about", "contacts"
    title = Column(String(255), nullable=False)
    meta_description = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, server_default=func.now(), nullable=True)
