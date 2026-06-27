"""
Парсер tinko.ru для документации по оборудованию СКУД
Парсит товары со страницы категории и ищет PDF на странице товара
10 параллельных Playwright-воркеров для скорости
"""

import asyncio
import hashlib
import json
import math
import re
from pathlib import Path
from urllib.parse import urljoin
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Browser

# ============================================================================
# КОНФИГ
# ============================================================================

CATEGORIES = [
    {
        "category_name": "СКУД",
        "url": "https://www.tinko.ru/catalog/category/114/",
    },
    {
        "category_name": "Охранно-пожарная сигнализация",
        "url": "https://www.tinko.ru/catalog/category/1/",
    },
    {
        "category_name": "Системы охранного телевидения",
        "url": "https://www.tinko.ru/catalog/category/265/",
    },
]
BASE_URL = "https://www.tinko.ru"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

STORAGE_DIR = Path("storage/documents/tinko")
MAX_CONCURRENT_DOWNLOADS = 5
REQUEST_TIMEOUT = httpx.Timeout(30.0, connect=20.0)
ALLOWED_EXTENSIONS = {".pdf"}

PER_PAGE = 12
PLAYWRIGHT_WORKERS = 5  # параллельных вкладок


# ============================================================================
# УТИЛИТЫ
# ============================================================================


def normalize_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def extract_filename_from_url(url: str) -> str:
    return url.split("?", 1)[0].rsplit("/", 1)[-1]


def has_allowed_extension(url: str) -> bool:
    filename = extract_filename_from_url(url).lower()
    return any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)


def detect_doc_type(url: str, link_text: str = "") -> str:
    text_lower = link_text.lower()
    url_lower = url.lower()

    if any(x in text_lower for x in ["datasheet", "спецификация", "spec"]):
        return "datasheet"
    if any(
        x in text_lower for x in ["manual", "инструкция", "руководство по эксплуатации"]
    ):
        return "manual"
    if any(
        x in text_lower
        for x in ["installation", "установка", "монтаж", "руководство по монтажу"]
    ):
        return "installation"
    if any(x in text_lower for x in ["паспорт"]):
        return "passport"
    if any(x in text_lower for x in ["реестр", "сертификат", "certificate"]):
        return "certificate"

    if "/datasheet/" in url_lower or "/spec/" in url_lower:
        return "datasheet"
    if "/manual/" in url_lower or "/guide/" in url_lower:
        return "manual"
    if "/installation/" in url_lower or "/install/" in url_lower:
        return "installation"

    return "pdf"


def calc_md5_from_file(path: Path) -> str:
    hasher = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


# ============================================================================
# HTTP ЗАПРОСЫ
# ============================================================================


async def fetch_page_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"[TINKO] Ошибка загрузки {url}: {e}")
        return None


# ============================================================================
# ОПРЕДЕЛЕНИЕ КОЛИЧЕСТВА СТРАНИЦ
# ============================================================================


def extract_total_products(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")

    for sel in [".page-title", "h1", ".catalog-title"]:
        for el in soup.select(sel):
            text = normalize_text(el.get_text(" ", strip=True))
            m = re.search(r"\((\d+)\)", text)
            if m:
                return int(m.group(1))

    text = normalize_text(soup.get_text(" ", strip=True))
    m = re.search(r"контроля и управления доступом\s*\((\d+)\)", text, re.I)
    if m:
        return int(m.group(1))

    return 0


async def get_max_page_number(client: httpx.AsyncClient, base_url: str) -> int:
    html = await fetch_page_html(client, base_url)
    if not html:
        return 1

    total = extract_total_products(html)
    if total <= 0:
        print("    ⚠️  Не удалось определить кол-во товаров, используем 1 страницу")
        return 1

    pages = math.ceil(total / PER_PAGE)
    print(f"    Всего товаров в категории: {total}, страниц: {pages}")
    return pages


# ============================================================================
# ПАРСИНГ СПИСКА ТОВАРОВ (только URL)
# ============================================================================


def parse_product_urls_from_page(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    seen = set()
    urls = []

    for link in soup.find_all("a", href=re.compile(r"/catalog/product/\d+")):
        href = link.get("href", "").strip()
        full_url = urljoin(BASE_URL, href)
        clean_url = full_url.split("?")[0]
        if not clean_url.endswith("/"):
            clean_url += "/"
        if clean_url not in seen:
            seen.add(clean_url)
            urls.append(clean_url)

    return urls


# ============================================================================
# ЗАГРУЗКА СТРАНИЦЫ ТОВАРА (PLAYWRIGHT)
# ============================================================================


async def fetch_product_data(
    browser: Browser,
    product_url: str,
) -> Optional[dict]:
    page = None
    try:
        page = await browser.new_page()
        await page.goto(product_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(1000)

        html = await page.content()
        soup = BeautifulSoup(html, "lxml")

        model_name = ""
        brand = ""

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if data.get("@type") == "Product":
                    model_name = normalize_text(data.get("name", ""))
                    brand_data = data.get("brand", {})
                    if isinstance(brand_data, dict):
                        brand = normalize_text(brand_data.get("name", ""))
                    elif isinstance(brand_data, str):
                        brand = normalize_text(brand_data)
                    break
            except Exception:
                pass

        if not model_name:
            h1 = soup.select_one("h1")
            if h1:
                model_name = normalize_text(h1.get_text(strip=True))

        if not model_name:
            return None

        pdf_links = []
        for link in soup.find_all("a"):
            href = link.get("href", "").strip()
            if not href:
                continue

            full_url = urljoin(BASE_URL, href)
            if not has_allowed_extension(full_url):
                continue

            link_text = normalize_text(link.get_text(strip=True))
            filename = extract_filename_from_url(full_url)

            pdf_links.append(
                {
                    "url": full_url,
                    "title": link_text or filename,
                    "filename": filename,
                    "doc_type": detect_doc_type(full_url, link_text),
                }
            )

        return {
            "model_name": model_name,
            "brand": brand,
            "product_url": product_url,
            "pdf_links": pdf_links,
        }

    except Exception as e:
        print(f"[TINKO] Ошибка загрузки товара {product_url}: {e}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


# ============================================================================
# ПАРАЛЛЕЛЬНЫЕ ВОРКЕРЫ
# ============================================================================


async def worker(
    browser: Browser,
    queue: asyncio.Queue,
    results: list,
    seen_docs: set,
    lock: asyncio.Lock,
    counter: list,
    total: int,
    category_name: str,
) -> None:
    while True:
        try:
            product_url = queue.get_nowait()
        except asyncio.QueueEmpty:
            break

        product_data = await fetch_product_data(browser, product_url)

        async with lock:
            counter[0] += 1
            i = counter[0]

        if not product_data:
            print(f"    [{i}/{total}] ❌ Пропускаю: {product_url}")
            await asyncio.sleep(0.2)
            continue

        model_name = product_data["model_name"]
        pdf_links = product_data["pdf_links"]

        if pdf_links:
            print(
                f"    [{i}/{total}] ✅ {model_name} ({product_data['brand']}) → {len(pdf_links)} PDF"
            )
        else:
            print(f"    [{i}/{total}] — {model_name}: PDF не найдено")

        async with lock:
            for pdf_link in pdf_links:
                key = (model_name, pdf_link["url"])
                if key in seen_docs:
                    continue
                seen_docs.add(key)
                results.append(
                    build_document_dict(product_data, pdf_link, category_name)
                )

        await asyncio.sleep(0.3)


# ============================================================================
# СКАЧИВАНИЕ ФАЙЛОВ
# ============================================================================


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest_dir: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, str]:
    async with semaphore:
        dest_dir.mkdir(parents=True, exist_ok=True)

        filename = extract_filename_from_url(url)
        local_path = dest_dir / filename

        if local_path.exists():
            file_hash = await asyncio.to_thread(calc_md5_from_file, local_path)
            return str(local_path), file_hash

        try:
            hasher = hashlib.md5()
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with local_path.open("wb") as f:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            hasher.update(chunk)
            return str(local_path), hasher.hexdigest()
        except Exception as e:
            print(f"[TINKO] Ошибка скачивания {filename}: {e}")
            if local_path.exists():
                local_path.unlink()
            raise


async def enrich_with_files(
    client: httpx.AsyncClient,
    docs: list[dict],
    download: bool,
) -> list[dict]:
    if not download:
        for doc in docs:
            doc["file_hash"] = None
        return docs

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
    tasks = [
        download_file(client, doc["file_url"], STORAGE_DIR, semaphore) for doc in docs
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for doc, result in zip(docs, results):
        if isinstance(result, Exception):
            print(f"[TINKO] Не удалось скачать {doc['file_url']}")
            doc["file_hash"] = None
        else:
            local_path, file_hash = result
            doc["file_hash"] = file_hash

    return docs


# ============================================================================
# ПРЕОБРАЗОВАНИЕ В ФОРМАТ БД
# ============================================================================


def build_document_dict(product_info: dict, pdf_link: dict, category_name: str) -> dict:
    return {
        "brand": product_info.get("brand") or "Unknown",
        "brand_website_url": "https://www.tinko.ru",
        "brand_logo_url": "",
        "category_name": category_name,
        "category_icon": "",
        "subcategory": "",
        "model_name": product_info.get("model_name", ""),
        "model_description": "",
        "model_spec": "{}",
        "model_image_url": "",
        "title": pdf_link.get("title", ""),
        "source_url": product_info.get("product_url", ""),
        "file_url": pdf_link.get("url", ""),
        "file_hash": "",
        "doc_type": pdf_link.get("doc_type", "pdf"),
        "parser_source": "tinko",
    }


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================


async def run(download: bool = False) -> list[dict]:
    print("=" * 70)
    print("🚀 [TINKO] Парсим документы СКУД / ОПС / Видео (несколько категорий)")
    print("=" * 70)

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)

    async with httpx.AsyncClient(
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    ) as client:
        try:
            all_documents: list[dict] = []
            seen_docs: set[tuple] = (
                set()
            )  # (model_name, file_url) — чтобы не дублировать

            for category in CATEGORIES:
                category_name = category["category_name"]
                category_url = category["url"]
                counter = [0]

                print("\n" + "-" * 70)
                print(f"📂 [TINKO] Категория: {category_name}")
                print("-" * 70)

                # ===== Шаг 1: Определяем кол-во страниц для категории =====
                print("📖 Определяем кол-во страниц...")
                max_page = await get_max_page_number(client, category_url)

                # ===== Шаг 2: Собираем URL всех товаров этой категории =====
                print(f"\n🛍️  Собираю URL товаров ({max_page} стр.)...")
                all_product_urls: list[str] = []
                seen_product_urls: set[str] = set()

                for page_num in range(1, max_page + 1):
                    page_url = (
                        category_url
                        if page_num == 1
                        else f"{category_url}?PAGEN_1={page_num}"
                    )

                    html = await fetch_page_html(client, page_url)
                    if not html:
                        print(f"    ❌ Страница {page_num}: не загрузилась")
                        continue

                    urls = parse_product_urls_from_page(html)
                    added = 0
                    for url in urls:
                        if url not in seen_product_urls:
                            seen_product_urls.add(url)
                            all_product_urls.append(url)
                            added += 1

                    print(
                        f"    Страница {page_num}/{max_page}: +{added} уникальных URL"
                    )
                    await asyncio.sleep(0.2)

                total = len(all_product_urls)
                print(f"    Всего уникальных товаров в '{category_name}': {total}")

                if total == 0:
                    continue

                # ===== Шаг 3: Параллельно загружаем страницы товаров =====
                print(
                    f"\n📄 Загружаю страницы товаров ({PLAYWRIGHT_WORKERS} воркеров)..."
                )

                queue: asyncio.Queue = asyncio.Queue()
                for url in all_product_urls:
                    await queue.put(url)

                lock = asyncio.Lock()

                workers = [
                    worker(
                        browser,
                        queue,
                        all_documents,
                        seen_docs,
                        lock,
                        counter,
                        total,
                        category_name,
                    )
                    for _ in range(PLAYWRIGHT_WORKERS)
                ]
                await asyncio.gather(*workers)

                print(
                    f"\n    Категория '{category_name}': документов накопилось всего {len(all_documents)}"
                )

            # ===== Шаг 4: Скачивание =====
            if download and all_documents:
                print(f"\n⬇️  [TINKO] Скачиваю {len(all_documents)} файлов...")
                all_documents = await enrich_with_files(
                    client, all_documents, download=True
                )
            else:
                all_documents = await enrich_with_files(
                    client, all_documents, download=False
                )
                if not download:
                    print("\n⏭️  [TINKO] Скачивание пропущено (download=False)")

            print("\n" + "=" * 70)
            print(f"✅ [TINKO] Готово! Документов: {len(all_documents)}")
            print("=" * 70)

            return all_documents

        finally:
            await browser.close()
            await playwright.stop()


# ============================================================================
# ТЕСТИРОВАНИЕ
# ============================================================================

if __name__ == "__main__":
    result = asyncio.run(run(download=False))
    print(f"\n📋 Всего найдено документов: {len(result)}")
    if result:
        print("\nПримеры:")
        for doc in result[:5]:
            print(
                f"  - [{doc['brand']}] {doc['model_name']} → {doc['title']} ({doc['doc_type']})"
            )
