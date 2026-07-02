from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database import get_db
from routes.auth import routes as auth_router
from routes.catalog import router as catalog_router


from services.news_service import save_news
from services.own_news_service import generate_topics_from_db, generate_and_save_news
from parsers.runner_doc import run_parser as run_doc
from parsers.runner_news import run_parser as run_news

scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


async def job_parse_docs():
    """Запускает все парсеры документации по очереди"""
    from parsers.runner_doc import PARSERS, run_parser as run_doc_parser

    for parser_name, parser_func in PARSERS:
        result = await run_doc_parser(parser_name, parser_func)
        print(f"[DOCS] {parser_name}: {result['status']}")


async def job_parse_and_rewrite():
    """Рерайт новостей с источников"""
    await run_news()


async def job_generate_own_news():
    """Генерация своих новостей через DeepSeek"""
    async for db in get_db():
        topics = await generate_topics_from_db(db, limit=1)
        await generate_and_save_news(db, topics)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(
        job_parse_docs,  # ← обёртка вместо run_doc
        CronTrigger(hour=2, minute=0, day="*/3"),
        id="parse_docs",  # ← убрал пробел
        replace_existing=True,
    )
    scheduler.add_job(
        job_parse_and_rewrite,
        CronTrigger(hour=9, minute=0),
        id="parse_news_morning",
        replace_existing=True,
    )
    scheduler.add_job(
        job_parse_and_rewrite,
        CronTrigger(hour=16, minute=0),
        id="parse_news_evening",
        replace_existing=True,  # ← добавил
    )
    scheduler.add_job(
        job_generate_own_news,
        CronTrigger(hour=22, minute=0),
        id="generate_own_news",
        replace_existing=True,
    )
    scheduler.start()
    print("[SCHEDULER] Запущен — 4 задачи активны")
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)


@app.post("/admin/run-news")
async def run_news_now():
    await job_parse_and_rewrite()
    return {"status": "done"}


@app.post("/admin/run-own-news")
async def run_own_news_now():
    await job_generate_own_news()
    return {"status": "done"}


@app.post("/admin/run-docs")
async def run_docs_now():
    await job_parse_docs()
    return {"status": "done"}


@app.get("/")
async def root():
    return {"message": "api run"}


app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(catalog_router)
