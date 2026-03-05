"""IEC 62446-3 report generation endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.inspection import Inspection

router = APIRouter()


@router.post("/generate/{inspection_id}")
async def generate_report(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Generate IEC 62446-3 compliant PDF report for an inspection."""
    inspection = await db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")

    # TODO: validate IEC conditions (irradiance >= 600 W/m², calibration, etc.)
    # TODO: generate PDF via services/report_generator.py
    # TODO: return download URL
    raise HTTPException(status_code=501, detail="Report generation not yet implemented")


@router.get("/download/{inspection_id}")
async def download_report(
    inspection_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """Download generated PDF report."""
    # TODO: fetch report from MinIO and stream
    raise HTTPException(status_code=501, detail="Not yet implemented")
