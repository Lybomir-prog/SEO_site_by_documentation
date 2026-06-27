import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urljoin
from services.document_service import detect_doc_type

import httpx
from bs4 import BeautifulSoup

DOCS_URL = "https://ironlogic.ru/web/ilBY.nsf/htm/ru_instructions"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
STORAGE_DIR = Path("storage/documents/iron_logic")  # куда скачиваем документы
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(
    30.0, connect=20.0
)  # сколько максимум ждем ответ от сервера


def normalize_text(value: str) -> str:
    """
    Убираем неразрывные пробелы и лишние обычные пробелы.
    Пример:
    ' Руководство\\xa0 по   эксплуатации ' -> 'Руководство по эксплуатации'
    """
    return " ".join(value.replace("\xa0", " ").split())


def extract_filename_from_url(url: str) -> str:
    """
    Берем только имя файла из ссылки, отрезая query-параметры.
    Пример:
    https://site.ru/files/doc.pdf?ver=2 -> doc.pdf
    """
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def is_pdf_url(url: str) -> bool:
    """Проверяем что ссылка ведет именно на pdf-файл."""
    return extract_filename_from_url(url).lower().endswith(".pdf")


async def fetch_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    """
    Загружаем страницу и сразу превращаем html в BeautifulSoup.
    Так потом удобнее искать теги и вытаскивать данные.
    """
    r = await client.get(url)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")


def calc_md5_from_file(path: Path) -> str:
    """
    Считаем md5 уже скачанного файла чанками.
    Так не держим весь pdf целиком в памяти.
    """
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Парсим страницу инструкций Iron Logic.

    Логика страницы такая:
    - h1 = общее название страницы, например 'Инструкции на оборудование'
    - далее в тексте идут названия подкатегорий
    - каждая строка документа заканчивается ссылкой "Скачать"
    - рядом со ссылкой лежат:
        название документа,
        модель / код,
        размер файла,
        дата
    """
    results = []

    page_title_tag = soup.find("h1")
    category_name = (
        normalize_text(page_title_tag.get_text(" ", strip=True))
        if page_title_tag
        else ""
    )

    known_subcategories = {
        "Автономные контроллеры",
        "Сетевые контроллеры",
        "Конвертеры",
        "Считыватели",
        "Настольные считыватели и адаптеры",
        "Электронные замки",
        "Снятые с производства",
        "Дополнительное оборудование",
        "Другие инструкции",
    }

    current_subcategory = ""

    for tag in soup.find_all(["div", "a"]):
        text = normalize_text(tag.get_text(" ", strip=True))

        # если встретили заголовок раздела — запоминаем
        if tag.name == "div" and text in known_subcategories:
            current_subcategory = text
            continue

        # интересуют только ссылки "Скачать"
        if tag.name != "a":
            continue

        link_text = normalize_text(tag.get_text(" ", strip=True))
        if link_text != "Скачать":
            continue

        href = tag.get("href", "").strip()
        if not href:
            continue

        file_url = urljoin(base_url, href)
        if not is_pdf_url(file_url):
            continue

        # ищем ближайший контейнер строки документа
        row = tag
        for _ in range(8):
            row = row.parent
            if row is None:
                break

            spans = row.find_all("span")
            if len(spans) >= 4:
                break

        if row is None:
            continue

        span_texts = [
            normalize_text(span.get_text(" ", strip=True))
            for span in row.find_all("span")
        ]
        span_texts = [x for x in span_texts if x and x != "Скачать"]

        if len(span_texts) < 4:
            continue

        # обычно:
        # [название..., модель/код, размер, дата]
        title = (
            " ".join(span_texts[:-3]).strip() if len(span_texts) > 3 else span_texts[0]
        )
        model_name = span_texts[-3] if len(span_texts) >= 3 else title

        filename = extract_filename_from_url(file_url)

        results.append(
            {
                "brand": "Iron Logic",
                "brand_website_url": "https://ironlogic.ru/",
                "brand_logo_url": "",
                "category_name": category_name,
                "category_icon": "",
                "subcategory": current_subcategory,
                "model_name": model_name or title or filename,
                "model_description": "",
                "model_spec": "{}",
                "model_image_url": "",
                "title": title or filename,
                "source_url": file_url,
                "file_url": file_url,
                "file_hash": "",
                "doc_type": detect_doc_type(file_url, title),
                "parser_source": "iron_logic",
            }
        )

    return results


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """
    Скачиваем один файл.
    Если файл уже есть — не качаем заново, а просто считаем md5.
    Возвращаем: (local_path, file_hash)
    """
    async with semaphore:
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = extract_filename_from_url(url)
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
    client: httpx.AsyncClient,
    docs: list[dict],
    download: bool,
) -> list[dict]:
    """
    Если download=False:
    - только парсим список документов
    - ничего не скачиваем

    Если download=True:
    - скачиваем файлы параллельно
    - записываем local_path и file_hash

    Если один файл не скачался,
    не роняем весь парсер — просто ставим None.
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
            print(f"[ОШИБКА] Не удалось скачать {doc['file_url']}: {result}")
            doc["local_path"] = None
            doc["file_hash"] = None
        else:
            local_path, file_hash = result
            doc["local_path"] = local_path
            doc["file_hash"] = file_hash

    return docs


async def run(download: bool = False) -> list[dict]:
    """
    Главная точка входа.

    download=False:
    - просто парсим страницу
    - получаем список документов без скачивания

    download=True:
    - парсим страницу
    - скачиваем pdf и считаем их md5
    """
    print("Iron Logic парсим", DOCS_URL)

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
            f"[{doc['subcategory']}] "
            f"{doc['model_name']} | "
            f"{doc['title']} | "
            f"{doc['file_url']}"
        )
