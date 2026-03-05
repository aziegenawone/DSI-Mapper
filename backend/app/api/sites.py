"""CRUD endpoints for PV sites (plants)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.site import Site

router = APIRouter()


class SiteCreate(BaseModel):
    name: str
    capacity_kw: float | None = None
    address: str | None = None
    client_name: str | None = None
    # boundary as GeoJSON string (for now)
    boundary_geojson: dict | None = None


class SiteResponse(BaseModel):
    id: uuid.UUID
    name: str
    capacity_kw: float | None
    address: str | None
    client_name: str | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[SiteResponse])
async def list_sites(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Site).order_by(Site.created_at.desc()))
    return result.scalars().all()


@router.post("/", response_model=SiteResponse, status_code=201)
async def create_site(data: SiteCreate, db: AsyncSession = Depends(get_db)):
    site = Site(
        name=data.name,
        capacity_kw=data.capacity_kw,
        address=data.address,
        client_name=data.client_name,
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(site_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    site = await db.get(Site, site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site
