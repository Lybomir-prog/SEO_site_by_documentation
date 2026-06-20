from sqlalchemy import Integer,ForeignKey,String,DateTime,Column
from sqlalchemy.orm import relationship
from database import Base
from sqlalchemy.sql import func

class DocumentDownloads(Base):
    __tablename__="document_downloads"

    id=Column(Integer,primary_key=True)
    document_id=Column(Integer,ForeignKey('document.id'),nullable=False)
    fingerprint=Column(String(500),nullable=False)#отпечаток браузера или пользователя
    ip_hash=Column(String(255))# хеш ip, потом можно просто ip
    created_at=Column(DateTime,server_default=func.now(),nullable=False)

    document=relationship("Document",back_populates="downloads")
