from sqlalchemy import Column,String,Integer,ForeignKey,DateTime,Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class DocumentVersion(Base):
    __tablename__= "document_versions"

    id= Column(Integer,primary_key=True)
    document_id=Column(Integer,ForeignKey("document.id"),nullable=False)

    version_number=Column(Integer,nullable=False,default=1)
    file_url=Column(String(255),nullable=False)#ссылка на файл
    file_hash=Column(String(255),nullable=False)#хеш для отслеживания изменений

    is_latest=Column(Boolean,nullable=False,default=True)#последняя версия документа или нет
    created_at=Column(DateTime,server_default=func.now(),nullable=False)

    document=relationship("Document",back_populates="versions")
