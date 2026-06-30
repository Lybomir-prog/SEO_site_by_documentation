import re
import hashlib

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from models.brands import Brands
from models.document import Document
from models.document_versions import DocumentVersion
from models.equipment_category import EquipmentCategory
from models.models import Models
from services.deepseek_service import process_document_ai
from transliterate import translit


def make_slug(value: str) -> str:
    try:
        value = translit(value, "ru", reversed=True)  # превращаем кириллицу в латиницу
    except Exception:
        pass

    slug = value.strip().lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9()_.-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")

    if len(slug) > 80:
        digest = hashlib.md5(slug.encode("utf-8")).hexdigest()[:8]
        slug = f"{slug[:71]}-{digest}"

    return slug


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

    if "/download/techspec/" in url_lower or "/spec/" in url_lower:
        return "techspec"
    if "/download/documentation/" in url_lower or "/manual/" in url_lower:
        return "documentation"
    if "/download/certificates/" in url_lower:
        return "certificate"

    return "pdf"


async def get_or_create_brand(
    db: AsyncSession,
    brand_name: str,
    website_url: str = "",
    logo_url: str = "",
) -> Brands:
    result = await db.execute(select(Brands).where(Brands.name_brand == brand_name))
    brand = result.scalar_one_or_none()

    if brand:
        return brand

    brand = Brands(
        name_brand=brand_name,
        slug=make_slug(brand_name),
        website_url=website_url,
        logo_url=logo_url,
    )
    db.add(brand)
    await db.flush()
    return brand


async def get_or_create_category(
    db: AsyncSession,
    category_name: str,
    icon: str = "",
    parent_id: int | None = None,
) -> EquipmentCategory | None:
    if not category_name:
        return None

    result = await db.execute(
        select(EquipmentCategory).where(
            EquipmentCategory.name_category == category_name,
            EquipmentCategory.parent_id == parent_id,
        )
    )
    category = result.scalar_one_or_none()

    if category:
        return category

    category = EquipmentCategory(
        name_category=category_name,
        slug=make_slug(category_name),
        icon=icon,
        parent_id=parent_id,
    )
    db.add(category)
    await db.flush()
    return category


async def get_or_create_model(
    db: AsyncSession,
    *,
    model_name: str,
    brand_id: int,
    category_id: int | None,
    description: str = "",
    spec: str = "{}",
    image_url: str = "",
) -> Models | None:
    if not model_name:
        return None

    result = await db.execute(
        select(Models).where(
            Models.name_equipment == model_name,
            Models.brand_id == brand_id,
        )
    )
    model = result.scalar_one_or_none()

    if model:
        model.updated_at = func.now()
        return model

    model = Models(
        category_id=category_id,
        brand_id=brand_id,
        description=description or "",
        spec=spec or "{}",
        name_equipment=model_name,
        slug=make_slug(model_name),
        image_url=image_url or "",
        is_active=True,
    )
    db.add(model)
    await db.flush()
    return model


async def get_document_by_source_url(
    db: AsyncSession,
    source_url: str,
) -> Document | None:
    result = await db.execute(select(Document).where(Document.source_url == source_url))
    return result.scalar_one_or_none()


async def create_document(
    db: AsyncSession,
    *,
    model_id: int | None,
    source_url: str,
    title: str,
    doc_type: str | None = None,
    parser_source: str | None = None,
) -> Document:
    # генерируем slug для запросов
    url_tail = source_url.rsplit("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
    slug_base = (
        f"{make_slug(title)}-{make_slug(url_tail)}" if url_tail else make_slug(title)
    )
    document = Document(
        model_id=model_id,
        source_url=source_url,
        title=title,
        doc_type=doc_type,
        parser_source=parser_source,
        slug=slug_base,
    )
    db.add(document)
    await db.flush()
    return document


async def get_latest_document_version(
    db: AsyncSession,
    document_id: int,
) -> DocumentVersion | None:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(desc(DocumentVersion.version_number))
    )
    return result.scalars().first()


async def create_document_version(
    db: AsyncSession,
    *,
    document_id: int,
    version_number: int,
    file_url: str,
    file_hash: str,
    is_latest: bool = True,
) -> DocumentVersion:
    version = DocumentVersion(
        document_id=document_id,
        version_number=version_number,
        file_url=file_url,
        file_hash=file_hash,
        is_latest=is_latest,
    )
    db.add(version)
    await db.flush()
    return version


async def deactivate_previous_versions(
    db: AsyncSession,
    document_id: int,
) -> None:
    result = await db.execute(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.is_latest == True,
        )
    )
    versions = result.scalars().all()

    for version in versions:
        version.is_latest = False

    await db.flush()


async def upsert_document_with_version(
    db: AsyncSession,
    item: dict[str, Any],
) -> dict[str, Any]:
    brand = await get_or_create_brand(
        db,
        brand_name=item["brand"],
        website_url=item.get("brand_website_url", ""),
        logo_url=item.get("brand_logo_url", ""),
    )

    category = await get_or_create_category(
        db,
        category_name=item.get("category_name", ""),
        icon=item.get("category_icon", ""),
    )

    subcategory = (
        await get_or_create_category(
            db,
            category_name=item.get("subcategory", ""),
            parent_id=category.id if category else None,
        )
        if item.get("subcategory")
        else None
    )

    effective_category = subcategory or category
    model = await get_or_create_model(
        db,
        model_name=item.get("model_name", ""),
        brand_id=brand.id,
        category_id=effective_category.id if effective_category else None,
        description=item.get("model_description", ""),
        spec=item.get("model_spec", "{}"),
        image_url=item.get("model_image_url", ""),
    )

    document = await get_document_by_source_url(db, item["source_url"])

    if not document:
        document = await create_document(
            db,
            model_id=model.id if model else None,
            source_url=item["source_url"],
            title=item["title"],
            doc_type=item.get("doc_type"),
            parser_source=item.get("parser_source"),
        )

        version = await create_document_version(
            db,
            document_id=document.id,
            version_number=1,
            file_url=item["file_url"],
            file_hash=item["file_hash"],
        )

        return {
            "status": "created",
            "document_id": document.id,
            "version_id": version.id,
            "version_number": version.version_number,
        }

    latest_version = await get_latest_document_version(db, document.id)

    if latest_version:
        same_hash = latest_version.file_hash == item["file_hash"]
        same_file_url = latest_version.file_url == item["file_url"]

        if same_hash and same_file_url and item["file_hash"] is not None:
            return {
                "status": "skipped",
                "document_id": document.id,
                "version_id": latest_version.id,
                "version_number": latest_version.version_number,
            }

        await deactivate_previous_versions(db, document.id)

        version = await create_document_version(
            db,
            document_id=document.id,
            version_number=latest_version.version_number + 1,
            file_url=item["file_url"],
            file_hash=item["file_hash"],
            is_latest=True,
        )

        return {
            "status": "updated",
            "document_id": document.id,
            "version_id": version.id,
            "version_number": version.version_number,
        }

    version = await create_document_version(
        db,
        document_id=document.id,
        version_number=1,
        file_url=item["file_url"],
        file_hash=item["file_hash"],
        is_latest=True,
    )

    return {
        "status": "version_created",
        "document_id": document.id,
        "version_id": version.id,
        "version_number": version.version_number,
    }


async def save_documents(
    db: AsyncSession,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    stats = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "version_created": 0,
        "errors": 0,
    }

    for item in items:
        try:
            async with db.begin_nested():
                result = await upsert_document_with_version(db, item)
            stats[result["status"]] += 1
            # внедряем описание сделанное нейросетью
            if result["status"] in ("created", "updated"):
                await process_document_ai(
                    db=db,
                    document_id=result["document_id"],
                    file_url=item["file_url"],
                    status=result["status"],
                )
        except Exception as e:
            stats["errors"] += 1
            print("save errors: ", item["source_url"], repr(e))

    await db.commit()
    return stats
