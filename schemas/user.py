from pydantic import BaseModel,EmailStr
from datetime import datetime

class UserCreate(BaseModel):#регистрация
    name: str
    login: str
    email: EmailStr
    password: str

class UserRead(BaseModel): #api возвращает клиенту
    id: int
    name: str
    login: str
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True

class UserLogin(BaseModel):#логин
    identifier : str #проверяем  логин или почта это
    password : str


