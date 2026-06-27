import feedparser
import re
from transliterate import translit


def make_news_slug(title: str) -> str:
    try:
        title = translit(title, "ru", reversed=True)
    except Exception:
        pass
    slug = title.strip().lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    return re.sub(r"-{2,}", "-", slug).strip("-")[:80]


def parser_rss(url: str):
    feed = feedparser.parse(url)
    items = []
    for entry in feed.entries:
        title = getattr(entry, "title", "")
        items.append(
            {
                "title": title,
                "link": getattr(entry, "link", ""),
                "published": getattr(entry, "published", ""),
                "summary": getattr(entry, "summary", ""),
                "slug": make_news_slug(title),  # ← добавить
            }
        )
    return items
