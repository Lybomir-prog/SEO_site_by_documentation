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
}  # только эти разделы берем


def normalize_text(value: str) -> str:
    return " ".join(
        value.replace("\xa0", " ").split()
    )  # delete space into text(удаляем неразрывные пробелы из текст)


def extract_filename_from_url(url: str) -> str:
    # берем только имя файла из url, отрезая querty-параметры(?foo=bar)
    # query-набор доп данных передаваемых сервером в ссылку через ? где он это блок параметров
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def is_pdf_url(url: str) -> str:
    return extract_filename_from_url(url).lower().endswith(".pdf")


def find_selection_table(heading) -> BeautifulSoup | None:
    """
    ищем первый <table> после заголовка h2,h3
    если до таблички встречаем другой заголовок- значит таблицы нет
    делаем это чтобы не захватить таблицу из след раздела
    """
    current = heading.find_next_sibling()

    while current:
        # встретили след заголовок раньше таблицы следовательно у этого раздела нет таблицы
        if current.name in {"h2", "h3"}:
            return None
        if current.name == "table":
            return current
        current = current.find_next_sibling()
    return current


async def fetch_page(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url)  # загружаем страницу и создаем суп для парсинга
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    парсим документацию со страницы:
    1. ищем заголовки h2,h3 которые входят в глобальную переменную
    2. после каждого заголовка ищем <table>
    3. в таблице каждая строка <tr> -один документ. первая ячейка название документа, вторая уже сама ссылка на файл
    вернем список словарей с метаданными
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
            cells = row.find_all("td")  # searh two cells: name|file
            if len(cells) < 2:
                continue

            title = normalize_text(
                cells[0].get_text(" ", strip=True)
            )  # пропускаем пустые строки и строки заголовки
            if not title or title.lower() == "название":
                continue

            link_tag = cells[1].find("a", href=True)  # ссылка на документ во 2 ячейке
            if not link_tag:
                continue

            href = link_tag.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(base_url, href)
            if not is_pdf_url(full_url):
                continue

            filename = extract_filename_from_url(full_url)

            result.append(
                {
                    "brand": "Sigur",
                    "brand_website_url": "https://sigur.com/",
                    "brand_logo_url": "",
                    "category_name": section_name,
                    "category_icon": "",
                    "model_name": filename.rsplit(".", 1)[
                        0
                    ],  # имя самого оборудования до точки в ссылке на скачивание
                    "model_description": "",
                    "model_spec": "{}",
                    "model_image_url": "",
                    "title": title,
                    "source_url": full_url,
                    "file_url": full_url,
                    "file_hash": "",
                    "doc_type": "pdf",
                    "parser_source": "sigur",
                    "filename": filename,
                }
            )
    return result


def calc_md5_from_file(path: Path) -> str:
    # читаем файл частями чтобы не загружать память и сервер в целом
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def download_file(
    client: httpx.AsyncClient, url: str, dest_dir: Path, semaphore: asyncio.Semaphore
) -> tuple[str, str]:
    """
    скачиваем один файл по url в папку dest_dir
    semaphore ограничивает количество одновременных скачиваний MAX_CONCURRENT_DOWNLOADS
    Если файл уже есть - пропускаем скачивание просто читаем хэш
    возвращаем путь к файлу и md5 hash
    """
    async with semaphore:
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = extract_filename_from_url(url)
        local_path = dest_dir / filename

        # файл уже скачан- считываем хеш и возвращаем
        if local_path.exists():
            file_hash = await asyncio.to_thread(calc_md5_from_file, local_path)
            return str(local_path), file_hash

        hasher = hashlib.md5()

        # скачиваем стримом чтобы не держать все пдф в памяти
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
    """
    download=True--- скачиваем все пдф файлы параллельно ограничивая семафором
    download=False--- просто проставляем local_path=None file_hash=None, только парсим
    если возникает ошибка, то она логируется в doc и получает None, а не ломает все
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
            print(f"ERRORS: не удалось скачать файл{doc['file_url']}:{result}")
            doc["local_path"] = None
            doc["file_hash"] = None
        else:
            local_path, file_hash = result
            doc["local_path"] = local_path
            doc["file_hash"] = file_hash

    return docs


async def run(download: bool = False) -> list[dict]:
    """
    точка входа
    download=True парсим + скачиваем файлы в storage/document/sigur
    download=False только парсим без скачивания
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


# делаем чтобы можно было просто проверить парсинг
if __name__ == "__main__":
    result = asyncio.run(run(download=False))
    print("итого загрузилось файлов:", len(result))
