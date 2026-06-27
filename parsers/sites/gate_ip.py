import asyncio
import hashlib
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from pathlib import Path
from services.document_service import detect_doc_type

DOCS_URL = "https://skd-gate.ru/materiali/tehnicheskaya_gate/dokumentaciya/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
STORAGE_DIR = Path("storage/documents/gate")  # куда скачиваем файлы
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(
    30.0, connect=20.0
)  # ждём не больше 30 секунд ответа от сервера


def normalize_text(value: str) -> str:
    """
    Убираем неразрывные пробелы (\xa0) и схлопываем лишние пробелы.
    Пример:
    '2.\xa0 Инструкции' -> '2. Инструкции'
    Нужно чтобы сравнение с ALLOWED_SECTIONS работало надёжно.
    """
    return " ".join(value.replace("\xa0", " ").split())


# Прогоняем через normalize_text сразу при объявлении —
# чтобы не думать о пробелах при сравнении с заголовками сайта
ALLOWED_SECTIONS = {
    normalize_text(s)
    for s in {
        "1. Руководства на ПО",
        "2. Инструкции",
        "3. Контроллеры доступа СКУД Gate",
        "4. Преобразователи интерфейсов СКУД Gate",
        "5. Иное оборудование Gate",
        "6. Интеграции Gate",
        "7. Архив устаревшей документации",
    }
}


def extract_filename_from_url(url: str) -> str:
    """
    Берём только имя файла из URL, отрезая query-параметры.
    Пример:
    https://skd-gate.ru/files/doc.pdf?ver=2 -> doc.pdf
    """
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def is_pdf_url(url: str) -> bool:
    """Проверяем что ссылка ведёт именно на PDF."""
    return extract_filename_from_url(url).lower().endswith(".pdf")


def calc_md5_from_file(path: Path) -> str:
    """
    Считаем MD5 файла чанками — чтобы не читать весь файл целиком в память.
    Используется когда файл уже скачан и нужно просто узнать его хэш.
    """
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def fetch_page(client: httpx.AsyncClient, url: str) -> BeautifulSoup:
    """Загружаем страницу и сразу превращаем HTML в объект BeautifulSoup для парсинга."""
    response = await client.get(url)
    response.raise_for_status()  # бросаем исключение если сервер вернул 4xx/5xx
    return BeautifulSoup(response.text, "lxml")


def parse_docs(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """
    Парсим таблицу с документацией Gate.

    Особенность сайта: вся документация находится в ОДНОЙ большой таблице.
    Структура такая:
        <tr> с <h3> внутри  ->  это заголовок раздела
        <tr> с текстом      ->  это строка с документом

    Поэтому идём по всем <tr> подряд и отслеживаем текущий раздел.
    Как только встречаем <h3> из ALLOWED_SECTIONS — запоминаем его как current_section.
    Все следующие строки с PDF-ссылками относим к этому разделу.
    Если встречаем заголовок не из ALLOWED_SECTIONS — сбрасываем current_section.
    """
    results = []
    current_section = ""  # название текущего активного раздела

    for row in soup.find_all("tr"):
        cells = row.find_all("td")

        if not cells:
            continue

        # Проверяем: может это строка-заголовок раздела (содержит h2 или h3)?
        heading = cells[0].find(["h2", "h3"])
        if heading:
            section_text = normalize_text(heading.get_text(" ", strip=True))

            if section_text in ALLOWED_SECTIONS:
                current_section = section_text  # раздел нам нужен — запоминаем
            else:
                current_section = (
                    ""  # раздел не нужен — сбрасываем, пропускаем его строки
                )

            continue

        # Если мы не внутри нужного раздела — пропускаем строку
        if not current_section:
            continue

        # Нужно минимум 2 ячейки: название документа | ссылка на файл
        if len(cells) < 2:
            continue

        title = normalize_text(cells[0].get_text(" ", strip=True))
        if not title:
            continue

        # В одной строке может быть несколько ссылок на PDF (разные версии/форматы)
        # поэтому берём все <a> из второй ячейки, а не только первую
        for link_tag in cells[1].find_all("a", href=True):
            href = link_tag.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(
                base_url, href
            )  # строим абсолютный URL из относительного

            if not is_pdf_url(full_url):
                continue  # пропускаем не-PDF ссылки

            filename = extract_filename_from_url(full_url)
            link_title = normalize_text(link_tag.get_text(" ", strip=True)) or filename

            results.append(
                {
                    "brand": "Gate",
                    "brand_website_url": "https://skd-gate.ru/",
                    "brand_logo_url": "",
                    "category_name": current_section,
                    "category_icon": "",
                    "subcategory": "",
                    "model_name": title,  # название строки таблицы = название модели/документа
                    "model_description": "",
                    "model_spec": "{}",
                    "model_image_url": "",
                    "title": link_title,  # текст ссылки или имя файла если текст пустой
                    "source_url": full_url,
                    "file_url": full_url,
                    "file_hash": "",  # заполнится после скачивания в enrich_docs_with_files
                    "doc_type": detect_doc_type(full_url, title),
                    "parser_source": "gate",
                    "filename": filename,
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
    Скачиваем один файл, возвращаем (путь к файлу, md5-хэш).
    Семафор ограничивает число одновременных скачиваний — не спамим сервер.
    Если файл уже есть на диске — не скачиваем повторно, только считаем хэш.
    """
    async with semaphore:
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = extract_filename_from_url(url)
        local_path = dest_dir / filename

        # Файл уже есть — просто читаем хэш и выходим
        if local_path.exists():
            file_hash = await asyncio.to_thread(calc_md5_from_file, local_path)
            return str(local_path), file_hash

        hasher = hashlib.md5()

        # Качаем стримом чтобы не держать весь PDF в памяти
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with local_path.open("wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        hasher.update(chunk)  # считаем хэш на лету пока качаем

        return str(local_path), hasher.hexdigest()


async def enrich_docs_with_files(
    client: httpx.AsyncClient,
    docs: list[dict],
    download: bool,
) -> list[dict]:
    """
    Если download=False — просто проставляем None в local_path и file_hash, не качаем.
    Если download=True — скачиваем все файлы параллельно и заполняем local_path + file_hash.
    Ошибка одного файла не роняет весь процесс — просто пишем None для этого документа.
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
    # gather запускает все скачивания параллельно, return_exceptions=True
    # означает что упавшие задачи не прерывают остальные — возвращают Exception как результат
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
    download=True  — парсим + скачиваем файлы в storage/documents/gate
    download=False — только парсим список документов без скачивания
    """
    print("Gate_ip парсим", DOCS_URL)

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
