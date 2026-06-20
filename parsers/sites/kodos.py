import requests
import hashlib
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin

DOCS_URL = "https://kodos.ru/podderzhka/dokumentacziya/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}  # говорим баузеру что это открывает человек, а не питон чтобы не блокировали доступ
STORAGE_DIR = "storage/documents/kodos"  # куда скачиваем


def fetch_page(url: str) -> BeautifulSoup:
    r = requests.get(
        url, headers=HEADERS, timeout=20
    )  # timeout-сколько секунд ждем, в случае если сервер не отвечает
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
        elif tag.name == "h3":
            current_subcategory = tag.get_text(strip=True)
        elif tag.name == "a":
            href = tag.get("href", "").strip()

            if not href:
                continue

            full_url = urljoin(base_url, href)
            if full_url.lower().endswith(".pdf"):
                title = tag.get_text(strip=True) or full_url.split("/")[-1]
                results.append(
                    {
                        "category": current_category,
                        "subcategory": current_subcategory,
                        "title": title,
                        "filename": full_url.split("/")[-1],
                        "source_url": base_url,
                        "file_url": full_url,
                    }
                )

    return results


def download_file(url: str, dest_dir: str) -> tuple[str, str]:
    """
    скачиваем файл, возвращаем: (local_path,file_hash)
    пропускаем файл если уже есть с таким именнем
    """
    os.makedirs(dest_dir, exist_ok=True)

    filename = url.split("/")[-1]
    local_path = os.path.join(dest_dir, filename)

    if os.path.exists(local_path):
        # файл уже скачан читаем хеш
        with open(local_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        return local_path, file_hash

    r = requests.get(url, headers=HEADERS, timeout=30, stream=True)
    r.raise_for_status()

    hasher = hashlib.md5()
    with open(local_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
                hasher.update(chunk)

    return local_path, hasher.hexdigest()


def run(download: bool = False) -> list[dict]:
    """
    download=True скачиваем файлы в storage/
    download=False только парсим список документов
    """
    print("КОДОС парсим", DOCS_URL)
    soup = fetch_page(DOCS_URL)
    docs = parse_docs(soup, DOCS_URL)
    print("Найдено документов", len(docs))

    for doc in docs:
        if download:
            try:
                local_path, file_hash = download_file(doc["file_url"], STORAGE_DIR)
                doc["local_path"] = local_path
                doc["file_hash"] = file_hash
            except Exception:
                doc["local_path"] = None
                doc["file_hash"] = None
        else:
            doc["local_path"] = None
            doc["file_hash"] = None
    return docs
