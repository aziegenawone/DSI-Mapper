import uuid
from typing import Optional
import enum

from geoalchemy2 import Geometry
from sqlalchemy import Float, ForeignKey, String, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class DefectType(str, enum.Enum):
    HOTSPOT = "hotspot"
    BYPASS_DIODE = "bypass_diode"
    CELL_DAMAGE = "cell_damage"
    PID = "pid"
    STRING_FAULT = "string_fault"
    SOILING = "soiling"
    SHADING = "shading"
    DELAMINATION = "delamination"
    OTHER = "other"


class IECClass(int, enum.Enum):
    """IEC 62446-3 defect severity classes based on delta-T."""
    CLASS_1 = 1  # dT < 10K — monitoring
    CLASS_2 = 2  # 10K <= dT < 20K — action needed
    CLASS_3 = 3  # dT >= 20K — urgent action


class DefectStatus(str, enum.Enum):
    OPEN = "open"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    REPLACED = "replaced"


class Defect(Base, UUIDMixin, TimestampMixin):
    """A defect detected on a PV module during an inspection."""

    __tablename__ = "defects"

    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("modules.id", ondelete="CASCADE")
    )
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inspections.id", ondelete="CASCADE")
    )
    # Defect location (centroid)
    geometry: Mapped[Optional[str]] = mapped_column(
        Geometry("POINT", srid=4326), nullable=True
    )
    defect_type: Mapped[DefectType] = mapped_column(SAEnum(DefectType))
    iec_class: Mapped[IECClass] = mapped_column(SAEnum(IECClass, create_constraint=False))
    delta_t_kelvin: Mapped[float] = mapped_column(Float)
    # Image references (URLs in MinIO)
    thermal_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    rgb_image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[DefectStatus] = mapped_column(
        SAEnum(DefectStatus), default=DefectStatus.OPEN
    )

    # Relationships
    module = relationship("Module", back_populates="defects")
    inspection = relationship("Inspection", back_populates="defects")
