import httpx
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import News
from parsers.base_news import NewsItem
from parsers.sites.securitylab import make_image_filename

IMAGE_BASE_DIR = Path("static/news/images")


async def _download_image(image_url: str) -> Optional[str]:
    try:
        now = datetime.now()
        save_dir = IMAGE_BASE_DIR / str(now.year) / f"{now.month:02d}"
        save_dir.mkdir(parents=True, exist_ok=True)

        filename = make_image_filename(image_url)
        filepath = save_dir / filename

        if filepath.exists():
            return str(filepath)

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(image_url)
            if resp.status_code == 200 and len(resp.content) > 1000:
                filepath.write_bytes(resp.content)
                return str(filepath)

    except Exception as e:
        print(f"[IMG ERROR] {image_url}: {e}")

    return None


async def save_news(db: AsyncSession, items: list[NewsItem]) -> dict:
    saved = skipped = updated = img_downloaded = 0

    for item in items:
        existing = (
            await db.execute(select(News).where(News.url_hash == item.url_hash))
        ).scalar_one_or_none()

        if existing:
            if existing.content_hash != item.content_hash:
                existing.content_original = item.content_original
                existing.content_hash = item.content_hash
                existing.title = item.title
                existing.summary = item.summary
                existing.image_url = item.image_url or existing.image_url
                existing.source_published_at = item.source_published_at
                updated += 1
            else:
                skipped += 1
            continue

        local_path = None
        img_downloaded_flag = False
        if item.image_url:
            local_path = await _download_image(item.image_url)
            if local_path:
                img_downloaded_flag = True
                img_downloaded += 1

        news = News(
            parser_source=item.parser_source,
            content_type=item.content_type,
            news_type=item.news_type,
            title=item.title,
            source_url=item.url,
            url_hash=item.url_hash,
            content_hash=item.content_hash,
            summary=item.summary,
            content_original=item.content_original,
            image_url=item.image_url,
            image_local_path=local_path,
            image_downloaded=img_downloaded_flag,
            source_published_at=item.source_published_at,
            brand_id=item.brand_id,
            is_published=False,
        )

        db.add(news)
        saved += 1

    await db.commit()

    return {
        "saved": saved,
        "skipped": skipped,
        "updated": updated,
        "images": img_downloaded,
    }
