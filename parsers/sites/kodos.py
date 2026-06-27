import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from services.document_service import detect_doc_type

DOCS_URL = "https://kodos.ru/podderzhka/dokumentacziya/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}  # говорим баузеру что это открывает человек, а не питон чтобы не блокировали доступ
STORAGE_DIR = Path("storage/documents/kodos")  # куда скачиваем
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(
    30.0, connect=20.0
)  # timeout-сколько секунд ждем, в случае если сервер не отвечает


async def fetch_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    r = await client.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    возвращаем список словарей:
    category, subcategory,filename,source_url
    """
    results = []
    current_category = ""
    current_subcategory = ""

    for tag in soup.find_all(["h2", "h3", "a"]):
        if tag.name == "h2":
            current_category = tag.get_text(strip=True)
            current_subcategory = ""
            continue

        elif tag.name == "h3":
            current_subcategory = tag.get_text(strip=True)
            continue

        href = tag.get("href", "").strip()
        if not href:
            continue

        full_url = urljoin(base_url, href)
        if not full_url.lower().endswith(".pdf"):
            continue

        title = tag.get_text(strip=True) or full_url.rsplit("/", 1)[-1]
        results.append(
            {
                "brand": "КОДОС",
                "brand_website_url": "https://kodos.ru/",
                "brand_logo_url": "",
                "category_name": current_category,
                "category_icon": "",
                "subcategory": current_subcategory,
                "model_name": title,
                "model_description": "",
                "model_spec": "{}",
                "model_image_url": "",
                "title": title,
                "source_url": full_url,
                "file_url": full_url,
                "file_hash": "",
                "doc_type": detect_doc_type(full_url, title),
                "parser_source": "kodos",
            }
        )

    return results


def calc_md5_from_file(path: Path) -> str:
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def download_file(
    client: httpx.AsyncClient, url: str, dest_dir: Path, semaphore: asyncio.Semaphore
) -> tuple[str, str]:
    """
    скачиваем файл, возвращаем: (local_path,file_hash)
    пропускаем файл если уже есть с таким именнем
    """
    # файл уже скачан читаем хеш
    async with semaphore:

        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = url.rsplit("/", 1)[-1]
        local_path = dest_dir / filename

        if local_path.exists():
            file_hash = await asyncio.to_thread(calc_md5_from_file, local_path)
            return str(local_path), file_hash

        hasher = hashlib.md5()

        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with local_path.open("wb") as f:
                async for chunk in r.aiter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)
        return str(local_path), hasher.hexdigest()


async def enrich_docs_with_files(
    client: httpx.AsyncClient, docs: list[dict], download: bool
) -> list[dict]:

    if not download:
        for doc in docs:
            doc["local_path"] = None
            doc["file_hash"] = None
        return docs

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    tasks = [
        download_file(client, doc["file_url"], STORAGE_DIR, semaphore) for doc in docs
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for doc, result in zip(docs, results):
        if isinstance(result, Exception):
            doc["local_path"] = None
            doc["file_hash"] = None
        else:
            local_path, file_hash = result
            doc["local_path"] = local_path
            doc["file_hash"] = file_hash

    return docs


async def run(download: bool = False) -> list[dict]:
    """
    download=True скачиваем файлы в storage/
    download=False только парсим список документов
    """
    print("КОДОС парсим", DOCS_URL)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:

        soup = await fetch_page(client, DOCS_URL)
        docs = parse_docs(soup, DOCS_URL)
        print("Найдено документов", len(docs))

        docs = await enrich_docs_with_files(client, docs, download=download)

        return docs


# делаем чтобы можно было просто проверить парсинг
if __name__ == "__main__":
    result = asyncio.run(run(download=False))
    print("итого загрузилось файлов:", len(result))
