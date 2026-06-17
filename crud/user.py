from datetime import datetime
from sqlalchemy import select,or_
from sqlalchemy.ext.asyncio import AsyncSession
from models.users import Users
from schemas.user import UserCreate
import bcrypt 


def hash_password(password:str)->str:
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode("utf-8")


def check_password(password:str,hashed_password:str)->bool:
    return bcrypt.checkpw(
        password.encode('utf-8'),
        hashed_password.encode('utf-8')
    )


async def get_users(db: AsyncSession):
    result= await db.execute(select(Users))
    return result.scalars().all()


async def get_user_by_id(db: AsyncSession, user_id: int):
    result= await db.execute(
        select(Users).where(Users.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_login(db: AsyncSession, login:str):
    result= await db.execute(
        select(Users).where(Users.login==login)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str):
    result= await db.execute(
        select(Users).where(Users.email==email)
    )
    return result.scalar_one_or_none()


async def get_user_by_login_or_email(db: AsyncSession, identifier:str):
    result= await db.execute(
        select(Users).where(
            or_(Users.login==identifier, Users.email==identifier)
        )
    )
    return result.scalar_one_or_none()


async def create_user(db : AsyncSession, data: UserCreate):
    user=Users(
        name=data.name,
        login=data.login,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_user(db: AsyncSession, identifier: str, password: str):
    user= await get_user_by_login_or_email(db, identifier)
    if not user:
        return None
    if not check_password(password, user.password_hash):
        return None
    return user


async def update_last_login(db: AsyncSession, user: Users):
    user.last_login_at=datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user: Users):
    await db.delete(user)
    await db.commit()