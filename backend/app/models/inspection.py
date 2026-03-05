import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.models.base import Base, TimestampMixin, UUIDMixin


class InspectionStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    VALIDATED = "validated"
    FAILED = "failed"


class Inspection(Base, UUIDMixin, TimestampMixin):
    """An inspection event on a site."""

    __tablename__ = "inspections"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE")
    )
    flight_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flights.id", ondelete="SET NULL"), nullable=True
    )
    inspection_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    operator_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[InspectionStatus] = mapped_column(
        SAEnum(InspectionStatus), default=InspectionStatus.UPLOADING
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # IEC 62446-3 required environmental conditions
    environmental_conditions: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="irradiance_wm2, ambient_temp_c, wind_speed_ms, wind_direction, humidity_pct, timestamp_start, timestamp_end",
    )
    # Instruments used (camera, drone, calibration certs)
    instruments: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="drone_model, camera_model, thermal_camera, calibration_cert_id, calibration_date",
    )

    # Relationships
    site = relationship("Site", back_populates="inspections")
    flight = relationship("Flight")
    defects = relationship(
        "Defect", back_populates="inspection", cascade="all, delete-orphan"
    )
