import asyncio
import hashlib
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

DOCS_URL = "https://www.perco.ru/partneram/dokumentatsiya.php"
BASE_URL = "https://www.perco.ru"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "X-Requested-With": "XMLHttpRequest",
}

STORAGE_DIR = Path("storage/documents/perco")
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=20.0)

# Крупные разделы документации.
# Пока вручную. Потом можно расширить, когда соберёшь остальные section slug.
SECTIONS = [
    "turnikety-kalitki-ograzhdeniya",
]

# Режим дедупликации:
# by_model -> сохраняем связь "категория + модель + файл"
# by_file  -> оставляем только уникальные file_url
DEDUPE_MODE = "by_model"

# Какие расширения считаем документами.
# Сейчас только PDF, потому что ты парсишь документацию.
# Если позже понадобятся BIM/CAD/архивы — добавишь сюда zip/rfa/dwg/stp.
ALLOWED_EXTENSIONS = {".pdf"}


def normalize_text(value: str) -> str:
    """Убираем неразрывные пробелы и схлопываем лишние пробелы."""
    return " ".join(value.replace("\xa0", " ").split())


def extract_filename_from_url(url: str) -> str:
    """Достаём имя файла из URL без query-параметров."""
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def has_allowed_extension(url: str) -> bool:
    """Проверяем, что ссылка ведёт на разрешённый тип файла."""
    filename = extract_filename_from_url(url).lower()
    return any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def detect_doc_type(url: str) -> str:
    """
    Определяем тип документа по URL.

    Это полезнее, чем всегда писать просто 'pdf',
    потому что дальше можно фильтровать техописания, руководства и сертификаты отдельно.
    """
    url_lower = url.lower()

    if "/download/techspec/" in url_lower:
        return "techspec"

    if "/download/documentation/" in url_lower:
        return "documentation"

    if "/download/certificates/" in url_lower:
        return "certificate"

    filename = extract_filename_from_url(url_lower)
    if filename.endswith(".pdf"):
        return "pdf"

    return "other"


def calc_md5_from_file(path: Path) -> str:
    """Считаем md5 уже скачанного файла."""
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


async def fetch_text(
    client: httpx.AsyncClient,
    url: str,
    method: str = "GET",
    data: dict | None = None,
    params: dict | None = None,
) -> str:
    """
    Универсальный HTTP-запрос, который возвращает текст ответа.
    Удобно использовать для endpoint'ов, отдающих HTML-фрагменты.
    """
    r = await client.request(method=method, url=url, data=data, params=params)
    r.raise_for_status()
    return r.text


async def fetch_subsections_html(client: httpx.AsyncClient, section_slug: str) -> str:
    """
    Получаем HTML со списком подкатегорий для крупного раздела.

    Например:
    section = turnikety-kalitki-ograzhdeniya

    Ответ содержит список вида:
    <li data-url="turnikety-tripody">Турникеты-триподы</li>

    Пока это скорее вспомогательная функция:
    сейчас select_products.php и так отдаёт весь HTML по section,
    но список подкатегорий может пригодиться для отладки и контроля структуры.
    """
    url = "https://www.perco.ru/partneram/select.php"
    params = {
        "section": section_slug,
        "archive": "",
    }
    return await fetch_text(client, url, method="GET", params=params)


def parse_subsections(html: str) -> list[dict]:
    """
    Разбираем HTML со списком подкатегорий.

    Возвращаем:
    [
        {"slug": "turnikety-tripody", "title": "Турникеты-триподы"},
        ...
    ]
    """
    soup = BeautifulSoup(html, "lxml")
    result = []

    for li in soup.select("li[data-url]"):
        slug = li.get("data-url", "").strip()
        title = normalize_text(li.get_text(" ", strip=True))

        if not slug or not title:
            continue

        result.append(
            {
                "slug": slug,
                "title": title,
            }
        )

    return result


async def fetch_products_html(
    client: httpx.AsyncClient,
    section_slug: str,
) -> str:
    """
    Получаем HTML со всеми моделями и документами по section.

    Важно:
    рабочий endpoint у PERCo — POST /partneram/select_products.php

    На текущем этапе достаточно section_slug:
    endpoint уже возвращает большой HTML со всеми категориями и моделями раздела.
    """
    url = "https://www.perco.ru/partneram/select_products.php"
    data = {
        "section": section_slug,
        "archive": "",
    }

    html = await fetch_text(client, url, method="POST", data=data)

    # Быстрая проверка, что мы попали в нужный HTML
    if (
        "dt-title" not in html
        and "download/documentation" not in html
        and "download/techspec" not in html
    ):
        print("[DEBUG] ответ от select_products.php не похож на список документов")
        print(html[:500])

    return html


def parse_docs_from_html(html: str, source_section: str = "") -> list[dict]:
    """
    Парсим HTML-фрагмент документации PERCo.

    Рабочая логика:
    - depth-3 -> категория
    - depth-4 -> модель
    - первый ul после depth-4 -> документы этой модели

    Почему не парсим просто все <a> подряд:
    потому что тогда легко привязать документы не к той модели.

    Почему не парсим через жёсткое recursive=False дерево:
    потому что HTML у PERCo местами рыхлый, и слишком строгая логика начинает терять документы.

    Поэтому тут компромисс:
    идём по заголовкам дерева по порядку и для каждой модели ищем ближайший ul,
    но останавливаемся, если раньше встретили следующий dt-title.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    current_category = source_section
    title_nodes = soup.select(".catalog-section-list div.dt-title")

    for title_div in title_nodes:
        classes = title_div.get("class", [])
        title_text = normalize_text(title_div.get_text(" ", strip=True))

        if not title_text:
            continue

        # depth-3 = товарная группа / категория
        if "depth-3" in classes:
            current_category = title_text
            continue

        # Нас интересуют только конкретные модели
        if "depth-4" not in classes:
            continue

        model_name = title_text

        # Ищем ближайший ul после модели.
        # Если раньше встретим следующий dt-title, значит документов у текущей модели не нашли.
        ul = None
        next_node = title_div.find_next()

        while next_node:
            if isinstance(next_node, Tag):
                node_classes = next_node.get("class", [])

                # Начался следующий заголовок дерева — прекращаем поиск ul для текущей модели
                if next_node.name == "div" and "dt-title" in node_classes:
                    break

                if next_node.name == "ul":
                    ul = next_node
                    break

            next_node = next_node.find_next()

        if not ul:
            continue

        for link_tag in ul.find_all("a", href=True):
            href = link_tag.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(BASE_URL, href)

            # Оставляем только нужные типы файлов
            if not has_allowed_extension(full_url):
                continue

            filename = extract_filename_from_url(full_url)
            title = normalize_text(link_tag.get_text(" ", strip=True)) or filename

            results.append(
                {
                    "brand": "PERCo",
                    "brand_website_url": "https://www.perco.ru/",
                    "brand_logo_url": "",
                    "category_name": "",
                    "category_icon": "",
                    "subcategory": current_category,
                    "model_name": model_name,
                    "model_description": "",
                    "model_spec": "{}",
                    "model_image_url": "",
                    "title": title,
                    "source_url": full_url,
                    "file_url": full_url,
                    "file_hash": "",
                    "doc_type": detect_doc_type(full_url),
                    "parser_source": "perco",
                    "filename": filename,
                }
            )

    return dedupe_docs(results, mode="by_model")


def dedupe_docs(docs: list[dict], mode: str = "by_model") -> list[dict]:
    """
    Дедупликация документов.

    mode="by_model":
        сохраняем один и тот же файл у разных моделей,
        потому что для БД это полезная связь "модель -> документ".

    mode="by_file":
        оставляем только уникальные file_url,
        если нужен просто список уникальных файлов.
    """
    unique_docs = []
    seen = set()

    for doc in docs:
        if mode == "by_file":
            key = doc["file_url"]
        else:
            key = (
                doc.get("subcategory", ""),
                doc["model_name"],
                doc["file_url"],
            )

        if key in seen:
            continue

        seen.add(key)
        unique_docs.append(doc)

    return unique_docs


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    """
    Скачиваем один файл.
    Если файл уже есть — повторно не скачиваем, только считаем md5.
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
        просто возвращаем документы без скачивания.

    Если download=True:
        скачиваем файлы и добавляем local_path + file_hash.
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
    Главный сценарий:
    1. Берём каждый section
    2. При желании смотрим список подкатегорий (для контроля структуры)
    3. Получаем большой HTML со всеми моделями и документами section
    4. Парсим документы
    5. Финально дедуплицируем в выбранном режиме
    6. При необходимости скачиваем файлы
    """
    print("PERCo парсим", DOCS_URL)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        all_docs = []

        print("Найдено разделов:", len(SECTIONS))

        for section_slug in SECTIONS:
            try:
                print(f"\n[SECTION] {section_slug}")

                # Это не обязательно для основного парсинга,
                # но полезно видеть, какие подкатегории есть у раздела.
                subsection_html = await fetch_subsections_html(client, section_slug)
                subsections = parse_subsections(subsection_html)
                print(f"  найдено подкатегорий: {len(subsections)}")

                html = await fetch_products_html(client, section_slug=section_slug)
                docs = parse_docs_from_html(html, source_section=section_slug)

                print(f"  найдено документов: {len(docs)}")
                all_docs.extend(docs)

            except Exception as e:
                print(f"[ОШИБКА] section={section_slug}: {e}")

        # Финальная дедупликация на уровне всего раздела/всех разделов
        final_docs = dedupe_docs(all_docs, mode=DEDUPE_MODE)

        print("\nИтого документов после дедупликации:", len(final_docs))

        final_docs = await enrich_docs_with_files(client, final_docs, download=download)
        return final_docs


if __name__ == "__main__":
    result = asyncio.run(run(download=False))
    print("\nИтого найдено документов:", len(result))

    # Показываем первые 10 для быстрой ручной проверки
    for doc in result[:10]:
        print(
            f"[{doc['category_name']}] "
            f"{doc['model_name']} -> {doc['title']} -> {doc['file_url']}"
        )
