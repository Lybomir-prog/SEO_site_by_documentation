import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path

# делается на подобии кодоса
DOCS_URL = "https://sigur.com/docs/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
STORAGE_DIR = Path("storage/documents/sigur")
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=20.0)

ALLOWED_SECTIONS = {
    "Документация на контроллеры",
    "Документация на считыватели",
    "Документация на программное обеспечение",
    "Документация на прочее оборудование",
    "Руководства по настройке интеграций",
}


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def extract_filename_from_url(url: str) -> str:
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def is_pdf_url(url: str) -> str:
    return extract_filename_from_url(url).lower().endswith(".pdf")


def find_selection_table(heading):
    current = heading.find_next_sibling()

    while current:
        if current.name in {"h2", "h3"}:
            return None
        if current.name == "table":
            return current
        current = current.find_next_subling()
    return current


async def fetch_page(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    result = []

    for heading in soup.find_all({"h2",'h3'}):
        section_name=normalize_text(heading.get_text(" ",strip=True))

        if section_name not in ALLOWED_SECTIONS:
            continue
        
        table=find_selection_table(heading)
        if not table:
            continue

        for row in table.find_all('tr'):
            cells=row.find_all("td")
            if len(cells)<2:
                continue

            title=normalize_text(cells[0].get_text(" ",strip=True))
            if not title or title.lower()=="название":
                continue

            link_tag=cells[1].find('a',href=True)
            if not link_tag:
                continue

            href=link_tag.get("href", "").strip()
            if not href:
                continue
            
            full_url=urljoin(base_url,href)
            if not is_pdf_url(full_url):
                continue

            filename=extract_filename_from_url(full_url)

            result.append(
                {
                    "brand": "Sigur",
                    "brand_website_url":
                }
            )
