import uuid
from datetime import date
from typing import Optional

from geoalchemy2 import Geometry
from sqlalchemy import Float, String, Date, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class Site(Base, UUIDMixin, TimestampMixin):
    """A photovoltaic plant / site."""

    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(255))
    # Plant boundary polygon in WGS84
    boundary: Mapped[Optional[str]] = mapped_column(
        Geometry("POLYGON", srid=4326), nullable=True
    )
    capacity_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    commissioning_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    client_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Flexible metadata: orientation, tilt, module_type, inverter_models, etc.
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    modules = relationship("Module", back_populates="site", cascade="all, delete-orphan")
    inspections = relationship(
        "Inspection", back_populates="site", cascade="all, delete-orphan"
    )
    flights = relationship("Flight", back_populates="site", cascade="all, delete-orphan")
