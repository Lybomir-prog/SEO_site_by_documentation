import httpx
import fitz
import chromadb
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.models import Models
from models.document import Document
from models.document_versions import DocumentVersion

load_dotenv()
# --------Инициализация--------
# services/deepseek_service.py — временно поменяй
llm = AsyncOpenAI(
    api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1"
)
# и модель

model = "deepseek-r1-distill-llama-70b"  # говорим где будет работать модель

embender = SentenceTransformer(
    "intfloat/multilingual-e5-base"
)  # говорим что текст мы будем преобразовывать в вектора, то есть ембенддинги
chroma = chromadb.PersistentClient(
    path=".chroma_db"
)  # база данных для хранения векторной информации, имеет искать слова похожие по смыслу
collection = chroma.get_or_create_collection("equimpent_docs")  # делаем коллекцию


# ---------PDF-> чанки-----
async def download_pdf(file_url: str, save_path: Path) -> bool:
    """install pdf if it's don't save"""
    if save_path.exist():
        return True
    try:
        async with httpx.Asynclient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(file_url)
            if resp.status_code == 200:
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_bytes(resp.content)
                return True
    except Exception as e:
        print(f"[PDF DOWNLOAD ERROR] {file_url} : {e}")
    return False


def extract_chunks(pdf_path: Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    chunks = []
    for page in doc:
        text = page.get_text().strip()
        for i in range(0, len(text), 500):
            chunk = text[i : i + 600].strip()
            if len(chunk) > 80:
                chunks.append(chunk)
    return chunks


# --------Индексация в Chromadb---
def index_chunks(equipment_key: str, chunks: list[str]):
    """индексируем чанки, предварительно удалив старые"""
    try:
        old = collection.get(where={"equipment_key": equipment_key})
        if old["ids"]:
            collection.delete(ids=old["ids"])
    except Exception:
        pass

    if not chunks:
        return

    embeddings = embender.endcode("chunks").tolist()
    collection.add(
        documents=chunks,
        embeddings=embeddings,
        ids=[f"{equipment_key}_{i}" for i in range(len(chunks))],
        metadatas=[{"equipment_key": equipment_key} for _ in chunks],
    )


def search_chunks(equipment_key: str, query: str, top_k: int = 6) -> str:
    query_emb = embender.encode([query]).tolist()
    results = collection.query(
        query_embeddings=query_emb,
        n_results=top_k,
        where={"equipment_key": equipment_key},
    )
    docs = results.get("documents", [[]])[0]
    return "\n\n".join(docs)


# ----Генерация текстов-----------
async def generate(system: str, user: str, temperature: float = 0.5) -> str:
    response = await llm.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    return response.choices[0].message.content.strip()


async def generate_model_descriptions(equipment_key: str, model_name: str) -> str:
    """SEO- описание модели оборудования по документам"""
    context = search_chunks(
        equipment_key, "технические характеристики назначение применение"
    )
    if not context:
        return ""

    return await generate(
        system="ТЫ SEO-копирайтер. Пишешь описания оборудования только на основе документациию. Не придумывай факты",
        user=f"""Напиши SEO-описание для страницы модели оборудования {model_name}
Требования:
- 150-200 слов
- Включи ключевые технические характеристики 
- Укажи область применения
- Естественные ключевые слова

Документация:{context}""",
        temperature=0.5,
    )


async def rewrite_news(title: str, content: str, news_type: str = "rewrite") -> str:
    """Рерайт/FAQ(часто задаваемые вопросы)/сравнение"""

    prompts = {
        "rewrite": f"""Перефразируй эту новость в уникальный SEO-текст.
        Стиль:деловой,150-200 слов,сохрани все факты.
        Заголовок:{title}
        Текст:{content}""",
        "faq": f"""По этому материалу составь FAQ: 5 вопросов и ответов
        Формат: **Вопрос** ... \n**Ответ:**...
        Материал:{title}\n{content}""",
        "comparsion": f"""Напиши статью-сравнение в формате таблица + вывод. 
        Данные: {title}\n{content}""",
    }

    return await generate(
        system="Ты SEO-копирайтер. Пишешь уникальные тексты на русском языке.",
        user=prompts.get(news_type, prompts["rewrite"]),
        temperature=0.75,
    )


# -----Основная точка входа в документ сервис--------
async def process_document_ai(
    db: AsyncSession,
    document_id: int,
    file_url: str,
    status: str,
) -> bool:
    """вызываем в document_service после upsert_document_with_version()
    Скачиваем PDF, индексируем, генерирует/обновляет описание модели."""
    if status not in ("created", "updated"):
        return False

    # получаем документ и его модель
    doc = await db.get(Document, document_id)
    if not doc or not doc.model_id:
        return False

    model = await db.get(Models, doc.model_id)
    if not model:
        return False

    equipment_key = f"model_{model.id}"
    pdf_path = Path(f"storage/document/{equipment_key}.pdf")

    # скачиваем пдф
    ok = await download_pdf(file_url, pdf_path)
    if not ok:
        print(f"[AI] не удалось скачать pdf: {file_url}")
        return False

    # индексируем чанки
    chunks = extract_chunks(pdf_path)
    index_chunks(equipment_key, chunks)

    # генерируем описание
    descriptions = await generate_model_descriptions(
        equipment_key, model.name_equipment
    )
    if descriptions:
        model.description = descriptions
        await db.commit()
        print(f"[AI] Описание обновленно:{model.name_equipment}")

    return True
