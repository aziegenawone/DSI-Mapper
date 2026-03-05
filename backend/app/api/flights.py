"""Flight planning, preview, and KMZ export endpoints."""

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.flight import Flight, FlightType
from app.services.flight_planner import (
    build_flight_plan,
    CAMERA_PRESETS,
    FlightPlan,
)

router = APIRouter()


# --- Pydantic models ---

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


class FlightPlanRequest(BaseModel):
    """Request body for flight plan generation/preview."""
    boundary_coords: list[list[float]]  # [[lat, lng], ...]
    num_rows: int = 10
    gsd_cm_px: float = 1.0
    camera_preset_key: str = "m30t"
    rotation_deg: float = 0.0
    is_vertical: bool = True
    zoom_ratio: float = 1.0
    object_height_m: float = 0.0
    flight_speed_ms: float = 3.0
    gimbal_pitch_deg: float = -90.0
    photo_interval_s: float = 1.0
    aircraft_yaw_deg: float = 0.0
    mission_name: str = "DSI Mapper Mission"


class WaypointResponse(BaseModel):
    latitude: float
    longitude: float
    altitude_agl: float
    heading_deg: float
    row_index: int


class FlightPlanResponse(BaseModel):
    """Flight plan preview data returned to frontend."""
    waypoints: list[WaypointResponse]
    altitude_agl: float
    altitude_above_object: float
    gsd_cm_px: float
    estimated_distance_m: float
    estimated_duration_s: float
    estimated_photos: int
    camera_name: str
    zoom_ratio: float
    flight_speed_ms: float
    num_rows: int


# --- Helper ---

def _build_plan(req: FlightPlanRequest) -> FlightPlan:
    """Build a FlightPlan from request parameters."""
    coords = [(c[0], c[1]) for c in req.boundary_coords]
    return build_flight_plan(
        boundary_coords=coords,
        num_rows=req.num_rows,
        gsd_cm_px=req.gsd_cm_px,
        camera_preset_key=req.camera_preset_key,
        rotation_deg=req.rotation_deg,
        is_vertical=req.is_vertical,
        zoom_ratio=req.zoom_ratio,
        object_height_m=req.object_height_m,
        flight_speed_ms=req.flight_speed_ms,
        gimbal_pitch_deg=req.gimbal_pitch_deg,
        photo_interval_s=req.photo_interval_s,
        aircraft_yaw_deg=req.aircraft_yaw_deg,
    )


# --- CRUD endpoints ---

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
    db.add(flight)
    await db.commit()
    await db.refresh(flight)
    return flight


# --- Flight plan preview (no DB required) ---

@router.get("/camera-presets")
async def get_camera_presets():
    """Return available camera presets for the flight planner UI."""
    return {
        key: {
            "name": p.name,
            "sensor_width_mm": p.sensor_width_mm,
            "image_width_px": p.image_width_px,
            "min_focal_length_mm": p.min_focal_length_mm,
            "max_focal_length_mm": p.max_focal_length_mm,
        }
        for key, p in CAMERA_PRESETS.items()
    }


@router.post("/plan/preview", response_model=FlightPlanResponse)
async def preview_flight_plan(req: FlightPlanRequest):
    """Generate a flight plan preview without saving to DB.

    Used by the frontend to display waypoints on the map in real-time
    as the user adjusts parameters.
    """
    try:
        plan = _build_plan(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FlightPlanResponse(
        waypoints=[
            WaypointResponse(
                latitude=wp.latitude,
                longitude=wp.longitude,
                altitude_agl=wp.altitude_agl,
                heading_deg=wp.heading_deg,
                row_index=wp.row_index,
            )
            for wp in plan.waypoints
        ],
        altitude_agl=plan.altitude_agl,
        altitude_above_object=plan.altitude_above_object,
        gsd_cm_px=plan.gsd_cm_px,
        estimated_distance_m=plan.estimated_distance_m,
        estimated_duration_s=plan.estimated_duration_s,
        estimated_photos=plan.estimated_photos,
        camera_name=plan.camera_preset.name,
        zoom_ratio=plan.zoom_ratio,
        flight_speed_ms=plan.flight_speed_ms,
        num_rows=req.num_rows,
    )


# --- KMZ export ---

@router.post("/plan/export-kmz")
async def export_flight_plan_kmz(req: FlightPlanRequest):
    """Generate and download a KMZ file from flight plan parameters.

    Does not require a saved flight — works directly from boundary + settings.
    """
    from dji.kmz_generator.converter import flight_plan_to_wpml_mission
    from dji.kmz_generator.exporter import export_kmz_bytes

    try:
        plan = _build_plan(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    mission = flight_plan_to_wpml_mission(plan, mission_name=req.mission_name)
    kmz_bytes = export_kmz_bytes(mission)

    return StreamingResponse(
        io.BytesIO(kmz_bytes),
        media_type="application/vnd.google-earth.kmz",
        headers={
            "Content-Disposition": f'attachment; filename="{req.mission_name}.kmz"'
        },
    )


@router.get("/{flight_id}/kmz")
async def export_saved_flight_kmz(
    flight_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Generate and download KMZ file for a saved flight."""
    flight = await db.get(Flight, flight_id)
    if not flight:
        raise HTTPException(status_code=404, detail="Flight not found")

    if not flight.waypoints:
        raise HTTPException(
            status_code=400,
            detail="Flight has no waypoints. Generate a plan first.",
        )

    # TODO: reconstruct FlightPlan from saved waypoints and generate KMZ
    raise HTTPException(status_code=501, detail="Saved flight KMZ export not yet implemented")
