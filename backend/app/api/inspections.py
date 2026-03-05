"""CRUD endpoints for inspections."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inspection import Inspection, InspectionStatus

router = APIRouter()


class InspectionCreate(BaseModel):
    site_id: uuid.UUID
    flight_id: uuid.UUID | None = None
    inspection_date: datetime
    operator_name: str | None = None
    environmental_conditions: dict | None = None
    instruments: dict | None = None


class InspectionResponse(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    inspection_date: datetime
    operator_name: str | None
    status: InspectionStatus
    environmental_conditions: dict | None
    instruments: dict | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[InspectionResponse])
async def list_inspections(
    site_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(Inspection).order_by(Inspection.inspection_date.desc())
    if site_id:
        query = query.where(Inspection.site_id == site_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=InspectionResponse, status_code=201)
async def create_inspection(
    data: InspectionCreate, db: AsyncSession = Depends(get_db)
):
    inspection = Inspection(**data.model_dump())
    db.add(inspection)
    await db.commit()
    await db.refresh(inspection)
    return inspection


@router.get("/{inspection_id}", response_model=InspectionResponse)
async def get_inspection(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    inspection = await db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection
