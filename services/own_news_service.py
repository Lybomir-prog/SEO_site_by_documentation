import random
import hashlib
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.brands import Brands
from models.equipment_category import EquipmentCategory
from models.models import Models
from models.news import News
from services.deepseek_service import rewrite_news
from services.document_service import make_slug

# ─── Шаблоны тем ──────────────────────────────────────────
# {brand}, {category}, {model} — подставляются из БД автоматически


TOPIC_TEMPLATES = [
    {
        "type": "faq",
        "title": "Частые вопросы о {brand}: что нужно знать перед покупкой",
        "content": "Бренд {brand}, оборудование категории {category}. Вопросы о надёжности, обслуживании, гарантии, запчастях.",
    },
    {
        "type": "faq",
        "title": "Как выбрать {category}: ответы на частые вопросы",
        "content": "Категория оборудования: {category}. Критерии выбора, технические характеристики, бюджет, применение.",
    },
    {
        "type": "faq",
        "title": "Гарантия и сервис {brand}: всё что нужно знать",
        "content": "Гарантийные условия бренда {brand}, сервисные центры, запчасти, {category}.",
    },
    {
        "type": "comparison",
        "title": "Сравнение моделей {brand} в категории {category}",
        "content": "Бренд {brand}, линейка {category}. Сравнение моделей по характеристикам, цене, области применения.",
    },
    {
        "type": "comparison",
        "title": "{model} и аналоги: что выбрать в 2026 году",
        "content": "Модель оборудования {model} от {brand}. Сравнение с конкурентами по ключевым параметрам.",
    },
    {
        "type": "comparison",
        "title": "Бюджетные vs премиум {category}: стоит ли переплачивать",
        "content": "Сравнение бюджетных и премиальных решений в категории {category}. Бренд {brand}.",
    },
    {
        "type": "rewrite",
        "title": "Обзор оборудования {brand}: актуальный каталог {category}",
        "content": "Бренд {brand} представляет линейку {category}. Обзор ассортимента, ключевые модели, преимущества.",
    },
    {
        "type": "rewrite",
        "title": "Новинки {brand} в 2026 году: что появилось в каталоге",
        "content": "Новые модели бренда {brand} в категории {category}. Характеристики, цены, сроки поставки.",
    },
    {
        "type": "rewrite",
        "title": "Почему {brand} — надёжный выбор для {category}",
        "content": "Преимущества бренда {brand} для {category}. Опыт применения, отзывы, технические особенности.",
    },
    {
        "type": "rewrite",
        "title": "Область применения {model}: где используют и почему",
        "content": "Модель {model} бренда {brand}. Сферы применения, преимущества, типичные задачи.",
    },
]


def make_title_hash(title: str) -> str:
    # хеш заголовка, чтобы проверить дубли
    return hashlib.md5(title.strip().lower().encode()).hexdigest()


async def get_recent_combinations(
    db: AsyncSession,
    days: int = 30,
) -> set[str]:
    """
    возвращается набор url_hash новостей за последние N дней
    используем чтобы не повторять комбинация бренд+шаблон
    """
    since = datetime.now() - timedelta(days=days)
    result = await db.execute(
        select(News.url_hash).where(
            and_(
                News.parser_source == "own_generated",
                News.created_at >= since,
            )
        )
    )
    return set(result.scalars().all())


async def title_exists(db: AsyncSession, title: str) -> bool:
    """проверяем есть ли уже новость с таким заголовком в бд"""
    title_hash = make_title_hash(title)
    result = await db.execute(
        select(News.id).where(News.url_hash == f"own_{title_hash}")
    )
    return result.scalar_one_or_none() is not None


async def generate_topics_from_db(
    db: AsyncSession,
    limit: int = 3,  # сколько статей сделать за раз
) -> list[dict]:
    """
    Берем случайные модели, категории и бренды из бд и собираем темы по шаблонам
    """
    # random brands
    brands_result = await db.execute(select(Brands).order_by(func.rand()).limit(10))
    brands = brands_result.scalars().all()

    # random categories
    categories_result = await db.execute(
        select(EquipmentCategory)
        .where(EquipmentCategory.parent_id.is_(None))
        .order_by(func.rand())
        .limit(10)
    )
    categories = categories_result.scalar().all()

    # random models
    models_result = await db.execute(select(Models).order_by(func.rand()).limit(10))
    models = models_result.scalars().all()

    if not brands or not categories:
        return []

    # недавно использованные комбинации
    recent_hashes = await get_recent_combinations(db, days=30)

    # перемешиваем шаблоны чтобы каждый день был разный тип
    shuffled_templates = TOPIC_TEMPLATES.copy()
    random.shuffle(shuffled_templates)

    topics = []
    attempts = 0
    max_attempts = limit * 10  # защита от бесконечного цикла

    while len(topics) < limit and attempts < max_attempts:
        attempts += 1

        brand = random.choice(brands)
        category = random.choice(categories)
        model = random.choice(models) if models else None

        # берем шаблон с учетом ротации
        template_index = len(topics) % len(shuffled_templates)
        template = shuffled_templates[template_index]

        title = template["title"].format(
            brand=brand.name_brand,
            category=category.name_category,
            model=model.name_equipment if model else brand.name_brand,
        )

        content = template["content"].format(
            brand=brand.name_brand,
            category=category.name_category,
            model=model.name_equipment if model else brand.name_brand,
        )

        title_hash = make_title_hash(title)
        url_hash = f"own_{title_hash}"

        # пропускаем если такой заголовок уже был
        if url_hash in recent_hashes:
            continue

        # пропускаем дубли в рамках текущего запуска
        if any(t["url_hash"] == url_hash for t in topics):
            continue

        recent_hashes.add(url_hash)  # резервируем

        topics.append(
            {
                "url_hash": url_hash,
                "slug": make_slug(title),
                "title": title,
                "content": content,
                "type": template["type"],
                "brand_id": brand.id,
            }
        )
    return topics


async def generate_and_save_news(
    db: AsyncSession,
    topics: list[dict],
) -> dict:
    saved = skipped = errors = 0
    for topic in topics:
        # финальная проверка в бд перед генерацией
        if await title_exists(db, topic["title"]):
            skipped += 1
            continue
        try:
            text = await rewrite_news(
                title=topic["title"],
                content=topic["content"],
                news_type=topic["type"],
            )

            db.add(
                News(
                    parser_source="own_generated",
                    content_type="article",
                    news_type=topic["type"],
                    title=topic["title"],
                    source_url=f"generated/{topic['slug']}",
                    url_hash=topic["url_hash"],
                    content_hash="",
                    content_original=topic["content"],
                    content_rewritten=text,
                    brand_id=topic.get("brand_id"),
                    is_published=False,
                )
            )
            saved += 1

        except Exception as e:
            errors += 1
        print(f"[OWN NEWS ERROR] {topic['title']}: {e}")

    await db.commit()
    return {"saved": saved, "skipped": skipped, "errors": errors}
