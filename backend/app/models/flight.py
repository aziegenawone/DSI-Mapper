import uuid
from typing import Optional
import enum

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, Integer, String, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class FlightType(str, enum.Enum):
    THERMAL_INSPECTION = "thermal_inspection"
    SERIAL_READING = "serial_reading"
    RGB_SURVEY = "rgb_survey"


class Flight(Base, UUIDMixin, TimestampMixin):
    """A planned or executed drone flight mission."""

    __tablename__ = "flights"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    flight_type: Mapped[FlightType] = mapped_column(SAEnum(FlightType))

    # Flight parameters
    altitude_m: Mapped[float] = mapped_column(Float)
    gsd_cm_px: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overlap_front_pct: Mapped[int] = mapped_column(Integer, default=80)
    overlap_side_pct: Mapped[int] = mapped_column(Integer, default=60)
    speed_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    camera_angle_deg: Mapped[float] = mapped_column(Float, default=90.0)  # 90 = nadir
    zoom_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Flight area (computed from site boundary + flight params)
    flight_area: Mapped[Optional[str]] = mapped_column(
        Geometry("POLYGON", srid=4326), nullable=True
    )

    # Waypoints and mission data
    waypoints: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        comment="Array of {lat, lon, alt, heading, actions: [{type, params}]}",
    )

    # KMZ file reference
    kmz_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Estimated mission stats
    estimated_duration_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_photos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_batteries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    site = relationship("Site", back_populates="flights")
