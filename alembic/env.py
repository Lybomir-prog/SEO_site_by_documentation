from logging.config import fileConfig
from alembic import context
from sqlalchemy import pool,create_engine
from config import settings
from database import Base
 #таким образом добавляем новые таблицы
from models.brands import Brands
from models.document import Document
from models.document_downloads import DocumentDownloads
from models.equipment_category import EquipmentCategory
from models.models import Models
from models.news_source import NewsSource
from models.news import News
from models.news_tags import NewsTags
from models.news_to_tags import NewsToTags
from models.reviews import Reviews
from models.reviews_likes import ReviewsLikes
from models.users import Users
from models.page_view import PageView

#python -m alembic.config init alembic СОЗДАЕМ ALEMBIC.INI
'''ПЕРЕД МИГРАЦИЕЙ СОЗДАЕМ БАЗУ
python -c "import pymysql; conn=pymysql.connect(host='localhost', user='root', password='Dtpeyxbr999', port=3306); cur=conn.cursor(); cur.execute('CREATE DATABASE IF NOT EXISTS ikb_site'); conn.commit(); cur.close(); conn.close(); print('database created')"
'''
#python -m alembic.config revision --autogenerate -m "initial tables"-ДЕЛАЕМ МИГРАЦИЮ 
#python -m alembic.config upgrade head ПРИМЕНИТЬ МИГРАЦИЮ

config=context.config
#config.set_main_option("sqlalchemy.url",settings.DATABASE_URL_SYNC)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata=Base.metadata

def run_migrations_offline()->None:
    #url=config.get_main_option("sqlalchemy.url")
    context.configure(
        url=settings.DATABASE_URL_SYNC,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
        },
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online()->None:
    connectable=create_engine(
        settings.DATABASE_URL_SYNC,
        poolclass=pool.NullPool
    )
    '''connectable=engine_from_config(
        config.get_section(config.config_ini_section,{}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )'''
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()