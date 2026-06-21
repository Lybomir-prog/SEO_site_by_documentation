import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path

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
}  # только эти разделы берем


def normalize_text(value: str) -> str:
    """
    Удаляем неразрывные пробелы и лишние обычные пробелы.
    Например:
    '  Документация\\xa0на   контроллеры  ' -> 'Документация на контроллеры'
    """
    return " ".join(value.replace("\xa0", " ").split())


def extract_filename_from_url(url: str) -> str:
    """
    Берем только имя файла из URL, отрезая query-параметры.
    Пример:
    https://site.ru/files/doc.pdf?ver=2 -> doc.pdf
    """
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def is_pdf_url(url: str) -> bool:
    """Проверяем, что ссылка ведет именно на PDF-файл."""
    return extract_filename_from_url(url).lower().endswith(".pdf")


def find_selection_table(heading) -> BeautifulSoup | None:
    """
    Ищем первую <table> после заголовка h2/h3.

    Если до таблицы встретится другой заголовок, значит у текущего раздела
    таблицы нет, и мы не должны случайно захватить таблицу из следующего блока.
    """
    current = heading.find_next_sibling()

    while current:
        if current.name in {"h2", "h3"}:
            return None
        if current.name == "table":
            return current
        current = current.find_next_sibling()

    return None


async def fetch_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    """Загружаем страницу и превращаем HTML в BeautifulSoup."""
    response = await client.get(url)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def build_sigur_doc(
    category_name: str,
    model_name: str,
    title: str,
    file_url: str,
    filename: str,
) -> dict:
    """
    Собираем итоговую запись документа в одном месте.
    Это удобно: если потом поменяется структура полей,
    достаточно будет править только эту функцию.
    """
    return {
        "brand": "Sigur",
        "brand_website_url": "https://sigur.com/",
        "brand_logo_url": "",
        "category_name": category_name,
        "category_icon": "",
        "model_name": model_name,
        "model_description": "",
        "model_spec": "{}",
        "model_image_url": "",
        "title": title,
        "source_url": file_url,
        "file_url": file_url,
        "file_hash": "",
        "doc_type": "pdf",
        "parser_source": "sigur",
        "filename": filename,
    }


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Парсим документацию со страницы.

    Логика:
    1. Ищем заголовки h2/h3, которые входят в ALLOWED_SECTIONS.
    2. После каждого такого заголовка ищем ближайшую таблицу.
    3. В таблице каждая строка <tr> — это один документ:
       - первая ячейка = название документа
       - вторая ячейка = ссылка на файл

    Возвращаем список словарей с метаданными.
    """
    result = []

    for heading in soup.find_all(["h2", "h3"]):
        section_name = normalize_text(heading.get_text(" ", strip=True))

        if section_name not in ALLOWED_SECTIONS:
            continue

        table = find_selection_table(heading)
        if not table:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")

            # Ожидаем минимум 2 ячейки: название | ссылка
            if len(cells) < 2:
                continue

            title = normalize_text(cells[0].get_text(" ", strip=True))

            # Пропускаем пустые строки и строку-заголовок таблицы
            if not title or title.lower() == "название":
                continue

            # Ссылка на документ должна быть во второй ячейке
            link_tag = cells[1].find("a", href=True)
            if not link_tag:
                continue

            href = link_tag.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(base_url, href)

            # Берем только PDF-документы
            if not is_pdf_url(full_url):
                continue

            filename = extract_filename_from_url(full_url)

            # Пока используем имя файла без расширения как model_name.
            # Потом, если понадобится, можно заменить эту логику
            # на извлечение из title или отдельный парсер модели.
            model_name = filename.rsplit(".", 1)[0]

            result.append(
                build_sigur_doc(
                    category_name=section_name,
                    model_name=model_name,
                    title=title,
                    file_url=full_url,
                    filename=filename,
                )
            )

    return result


def calc_md5_from_file(path: Path) -> str:
    """
    Считаем MD5 файла чанками, чтобы не читать весь файл целиком в память.
    """
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """
    Скачиваем один файл по URL в папку dest_dir.

    semaphore ограничивает число одновременных скачиваний.
    Если файл уже существует, не скачиваем заново — только считаем его MD5.

    Возвращаем:
    (путь к файлу, md5-хэш)
    """
    async with semaphore:
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = extract_filename_from_url(url)
        local_path = dest_dir / filename

        # Если файл уже есть, просто читаем его хэш
        if local_path.exists():
            file_hash = await asyncio.to_thread(calc_md5_from_file, local_path)
            return str(local_path), file_hash

        hasher = hashlib.md5()

        # Качаем стримом, чтобы не держать весь PDF в памяти
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with local_path.open("wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)

        return str(local_path), hasher.hexdigest()


async def enrich_docs_with_files(
    client: httpx.AsyncClient,
    docs: list[dict],
    download: bool,
) -> list[dict]:
    """
    download=True:
    - скачиваем все PDF параллельно, ограничивая число потоков семафором

    download=False:
    - только парсим, ничего не скачиваем

    Если для отдельного файла возникла ошибка, не роняем весь процесс:
    просто записываем local_path=None и file_hash=None.
    """
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
            print(f"ERROR: не удалось скачать файл {doc['file_url']}: {result}")
            doc["local_path"] = None
            doc["file_hash"] = None
        else:
            local_path, file_hash = result
            doc["local_path"] = local_path
            doc["file_hash"] = file_hash

    return docs


async def run(download: bool = False) -> list[dict]:
    """
    Точка входа.

    download=True:
    - парсим страницу
    - скачиваем файлы в storage/documents/sigur

    download=False:
    - только парсим список документов
    """
    print("Sigur парсим", DOCS_URL)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        soup = await fetch_page(client, DOCS_URL)
        docs = parse_docs(soup, DOCS_URL)
        print("Найдено документов:", len(docs))

        docs = await enrich_docs_with_files(client, docs, download=download)
        return docs


if __name__ == "__main__":
    result = asyncio.run(run(download=False))
    print("Итого найдено файлов:", len(result))

    for doc in result[:10]:
        print(
            f"[{doc['category_name']}] "
            f"{doc['model_name']} | "
            f"{doc['title']} | "
            f"{doc['file_url']}"
        )
