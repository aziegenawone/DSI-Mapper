"""Serial number reading pipeline endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inspection import Inspection

router = APIRouter()


class SerialResult(BaseModel):
    module_id: uuid.UUID
    serial_number: str | None
    confidence: float
    needs_review: bool


@router.post("/process/{inspection_id}")
async def process_serials(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Run serial reading pipeline on RGB images from an inspection.

    Pipeline: label detection (YOLO) → crop → super-resolution (Real-ESRGAN) → OCR (EasyOCR)
    """
    inspection = await db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # TODO: trigger Celery task for serial reading pipeline
    raise HTTPException(status_code=501, detail="Serial reading not yet implemented")


@router.get("/results/{inspection_id}", response_model=list[SerialResult])
async def get_serial_results(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Get serial reading results for an inspection."""
    # TODO: query modules with serial numbers for this inspection
    raise HTTPException(status_code=501, detail="Not yet implemented")
