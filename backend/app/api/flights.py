"""Flight planning and KMZ export endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.flight import Flight, FlightType

router = APIRouter()


class FlightCreate(BaseModel):
    site_id: uuid.UUID
    name: str
    flight_type: FlightType
    altitude_m: float
    overlap_front_pct: int = 80
    overlap_side_pct: int = 60
    speed_ms: float | None = None
    camera_angle_deg: float = 90.0
    zoom_level: float | None = None


class FlightResponse(BaseModel):
    id: uuid.UUID
    site_id: uuid.UUID
    name: str
    flight_type: FlightType
    altitude_m: float
    gsd_cm_px: float | None
    overlap_front_pct: int
    overlap_side_pct: int
    estimated_duration_min: float | None
    estimated_photos: int | None
    kmz_url: str | None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[FlightResponse])
async def list_flights(
    site_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(Flight).order_by(Flight.created_at.desc())
    if site_id:
        query = query.where(Flight.site_id == site_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=FlightResponse, status_code=201)
async def create_flight(data: FlightCreate, db: AsyncSession = Depends(get_db)):
    flight = Flight(**data.model_dump())
    # TODO: compute waypoints, GSD, estimated duration/photos/batteries
    # via services/flight_planner.py
    db.add(flight)
    await db.commit()
    await db.refresh(flight)
    return flight


@router.get("/{flight_id}/kmz")
async def export_kmz(flight_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Generate and download KMZ file for DJI Pilot 2."""
    flight = await db.get(Flight, flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")
    # TODO: generate KMZ via dji/kmz_generator
    raise HTTPException(status_code=501, detail="KMZ generation not yet implemented")
