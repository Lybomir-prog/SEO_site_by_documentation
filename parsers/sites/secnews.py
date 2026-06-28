import feedparser
import httpx
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional

from parsers.base_news import NewsItem
from parsers.sites.securitylab import (
    make_url_hash,
    make_content_hash,
    normalize_text,
    make_image_filename,
)

RSS_URL = "http://secnews.ru/rss/news.xml"
SOURCE_NAME = "SecNews"
PARSER_KEY = "secnews_rss"


def _parse_og_image(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", property="og:image")
    if tag and tag.get("content"):
        return tag["content"]
    img = soup.select_one("article img, .post-content img, .entry-content img")
    return img.get("src") if img else None


def _parse_full_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    article = soup.select_one("article, .post-content, .entry-content, .article-body")
    raw = (
        article.get_text(separator="\n", strip=True)
        if article
        else soup.get_text(separator="\n", strip=True)[:5000]
    )
    return normalize_text(raw)


async def fetch_news(limit: int = 20) -> list[NewsItem]:
    feed = feedparser.parse(RSS_URL)
    results: list[NewsItem] = []

    async with httpx.AsyncClient(
        timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
    ) as client:
        for entry in feed.entries[:limit]:
            try:
                pub_date = None
                if hasattr(entry, "published"):
                    try:
                        pub_date = parsedate_to_datetime(entry.published)
                    except Exception:
                        pub_date = datetime.now()

                resp = await client.get(entry.link)
                html = resp.text

                image_url = _parse_og_image(html)
                full_text = _parse_full_text(html)
                summary_raw = BeautifulSoup(
                    getattr(entry, "summary", ""), "html.parser"
                ).get_text(strip=True)[:500]
                summary = normalize_text(summary_raw)
                title = normalize_text(entry.title)

                results.append(
                    NewsItem(
                        source_name=SOURCE_NAME,
                        source_type="rss",
                        content_type="news",
                        news_type="general",
                        parser_source=PARSER_KEY,
                        title=title,
                        url=entry.link,
                        url_hash=make_url_hash(entry.link),
                        content_hash=make_content_hash(title, full_text),
                        summary=summary,
                        content_original=full_text,
                        image_url=image_url,
                        source_published_at=pub_date,
                    )
                )
            except Exception as e:
                print(f"[SECNEWS ERROR] {entry.link}: {e}")

    return results
