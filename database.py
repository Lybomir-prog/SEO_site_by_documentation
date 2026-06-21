from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import settings

# python -m alembic.config init alembic СОЗДАЕМ ALEMBIC.INI
# python -m alembic.config revision --autogenerate -m "initial tables"-ДЕЛАЕМ МИГРАЦИЮ
# python -m alembic.config upgrade head ПРИМЕНИТЬ МИГРАЦИЮ

engine = create_async_engine(settings.DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
