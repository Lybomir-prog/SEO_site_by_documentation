from sqlalchemy import Column,Integer,ForeignKey,Text,String,Boolean,DateTime
from database import Base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

class Document(Base):
    __tablename__='document'

    id=Column(Integer,primary_key=True)
    model_id=Column(Integer,ForeignKey("models.id"))
    version=Column(Integer,nullable=False)
    version_number=Column(Integer,default=1)
    file_url=Column(String(255),nullable=False)
    file_hash=Column(String(255),nullable=False)
    is_latest=Column(Boolean,default=True)
    source_url=Column(String(255),nullable=False)
    created_at=Column(DateTime,server_default=func.now(),nullable=False)
    model=relationship("Models",back_populates="documents")
    downloads=relationship("DocumentDownloads",back_populates="document")