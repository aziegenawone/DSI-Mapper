"""Image upload and processing trigger endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inspection import Inspection, InspectionStatus

router = APIRouter()


class ProcessingStatus(BaseModel):
    inspection_id: uuid.UUID
    status: InspectionStatus
    progress_pct: float | None = None
    current_step: str | None = None

    model_config = {"from_attributes": True}


@router.post("/upload/{inspection_id}")
async def upload_images(
    inspection_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload drone images (R-JPEG thermal + RGB) for an inspection."""
    inspection = await db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # TODO: save files to MinIO, extract EXIF/GPS metadata,
    # trigger Celery processing pipeline
    uploaded = []
    for f in files:
        # Placeholder: store to MinIO
        uploaded.append({"filename": f.filename, "size": f.size})

    return {"uploaded": len(uploaded), "files": uploaded}


@router.get("/status/{inspection_id}", response_model=ProcessingStatus)
async def processing_status(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Check processing pipeline status."""
    inspection = await db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return ProcessingStatus(
        inspection_id=inspection.id,
        status=inspection.status,
    )
