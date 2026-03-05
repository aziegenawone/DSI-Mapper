import uuid
from datetime import date
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Float, Integer, String, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Module(Base, UUIDMixin, TimestampMixin):
    """A single PV module (panel) as a persistent digital twin asset."""

    __tablename__ = "modules"

    site_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE")
    )
    # Panel footprint polygon in WGS84
    geometry: Mapped[Optional[str]] = mapped_column(
        Geometry("POLYGON", srid=4326), nullable=True
    )
    # Position within the plant layout
    row_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    col_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    string_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    inverter_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Serial number (populated by serial reading pipeline)
    serial_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Module specs
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    module_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    installation_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Relationships
    site = relationship("Site", back_populates="modules")
    defects = relationship("Defect", back_populates="module", cascade="all, delete-orphan")
