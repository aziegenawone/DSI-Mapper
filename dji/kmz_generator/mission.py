"""Data models for DJI waypoint missions."""

from dataclasses import dataclass, field
from enum import Enum


class CameraActionType(str, Enum):
    TAKE_PHOTO = "takePhoto"
    START_RECORD = "startRecord"
    STOP_RECORD = "stopRecord"
    ZOOM = "zoom"
    GIMBAL_ROTATE = "gimbalRotate"


@dataclass
class CameraAction:
    action_type: CameraActionType
    # For gimbal rotation
    gimbal_pitch_deg: float | None = None  # -90 = nadir
    # For zoom
    zoom_ratio: float | None = None


@dataclass
class Waypoint:
    latitude: float   # WGS84 decimal degrees
    longitude: float  # WGS84 decimal degrees
    altitude_m: float  # Relative to takeoff point (AGL)
    heading_deg: float = 0.0  # Aircraft heading (0=North, 90=East)
    speed_ms: float | None = None  # Override mission speed at this waypoint
    actions: list[CameraAction] = field(default_factory=list)


@dataclass
class WaypointMission:
    """A complete waypoint mission for DJI Pilot 2."""
    name: str
    waypoints: list[Waypoint]
    # Global mission parameters
    auto_flight_speed_ms: float = 5.0
    max_flight_speed_ms: float = 10.0
    # Finish action: goHome, hover, land
    finish_action: str = "goHome"
    # Heading mode: auto, fixed, manual, waypoint
    heading_mode: str = "waypoint"
    # Camera settings
    camera_angle_deg: float = -90.0  # -90 = nadir
    photo_interval_s: float | None = None  # Time interval for auto photo
    photo_distance_m: float | None = None  # Distance interval for auto photo

    @property
    def estimated_distance_m(self) -> float:
        """Estimate total flight distance in meters."""
        if len(self.waypoints) < 2:
            return 0.0
        from math import radians, sin, cos, sqrt, atan2

        total = 0.0
        for i in range(len(self.waypoints) - 1):
            w1, w2 = self.waypoints[i], self.waypoints[i + 1]
            # Haversine formula
            lat1, lat2 = radians(w1.latitude), radians(w2.latitude)
            dlat = lat2 - lat1
            dlon = radians(w2.longitude - w1.longitude)
            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            total += 6371000 * 2 * atan2(sqrt(a), sqrt(1 - a))
        return total

    @property
    def estimated_duration_s(self) -> float:
        """Estimate flight duration in seconds."""
        if self.auto_flight_speed_ms <= 0:
            return 0.0
        return self.estimated_distance_m / self.auto_flight_speed_ms
