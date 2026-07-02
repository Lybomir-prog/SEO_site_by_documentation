from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.equipment_category import EquipmentCategory

router = APIRouter(tags=["catalog"])
templates = Jinja2Templates(directory="templates")


@router.get("/catalog/", response_class=HTMLResponse, name="catalog_index")
async def catalog_index(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(EquipmentCategory)
        .where(
            EquipmentCategory.parent_id.is_(None),
            EquipmentCategory.is_active.is_(True),
        )
        .order_by(EquipmentCategory.name_category.asc())
    )
    categories = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="static/catalog/index.html",
        context={
            "categories": categories,
            "meta_title": "Каталог оборудования",
            "meta_description": "Каталог оборудования по категориям и брендам с документацией, описаниями и техническими характеристиками",
        },
    )
