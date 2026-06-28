import asyncio
from database import AsyncSessionLocal, engine
from parsers.sites.securitylab import fetch_news as fetch_securitylab
from parsers.sites.secnews import fetch_news as fetch_secnews
from services.news_service import save_news


async def run_all():
    print("[NEWS] Старт парсинга...")

    async with AsyncSessionLocal() as db:
        # SecurityLab
        items1 = await fetch_securitylab(limit=20)
        print(f"[NEWS][SecurityLab] Найдено: {len(items1)}")
        stats1 = await save_news(db, items1)
        print(
            f"[SecurityLab] saved={stats1['saved']}, "
            f"skipped={stats1['skipped']}, "
            f"updated={stats1['updated']}, "
            f"images={stats1['images']}"
        )

        # SecNews
        items2 = await fetch_secnews(limit=20)
        print(f"[NEWS][SecNews] Найдено: {len(items2)}")
        stats2 = await save_news(db, items2)
        print(
            f"[SecNews] saved={stats2['saved']}, "
            f"skipped={stats2['skipped']}, "
            f"updated={stats2['updated']}, "
            f"images={stats2['images']}"
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_all())
