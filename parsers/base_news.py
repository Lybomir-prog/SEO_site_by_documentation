from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsItem:
    source_name: str
    source_type: str  # rss | html
    content_type: str  # news | update | insight
    news_type: str  # new_model | certificate | compatibility | general
    parser_source: str  # securitylab_rss / secnews_rss

    title: str
    url: str
    url_hash: str  # md5(url)
    content_hash: str  # md5(title + content)

    summary: str = ""
    content_original: str = ""
    content_rewritten: Optional[str] = None

    image_url: Optional[str] = None
    image_local_path: Optional[str] = None

    source_published_at: Optional[datetime] = None
    brand_id: Optional[int] = None
