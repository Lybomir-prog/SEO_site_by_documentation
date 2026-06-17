from fastapi import APIRouter,Depends,HTTPException,status
from database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from schemas.user import UserCreate,UserLogin,UserRead
from crud.user import get_user_by_email,get_user_by_login,create_user,login_user,update_last_login


routes=APIRouter(prefix="/auth",tags=["Auth"])


@routes.post('/register', response_model=UserRead ,status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db:AsyncSession=Depends(get_db)):
    existing_login= await get_user_by_login(db, data.login)
    if existing_login:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Логин уже существует'
        )
    existing_email= await get_user_by_email(db,data.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Электронная почта уже существует"
        )
    user=await create_user(db,data)
    return user


@routes.post('/login')
async def login(data:UserLogin, db:AsyncSession=Depends(get_db)):
    user=await login_user(db,data.identifier,data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="неверный логин/почта или пароль"
        )
    await update_last_login(db, user)
    return {
        "message":"Успешный вход",
        "user_id":user.id,
        "login":user.login,
        "email": user.email
    }
