"""Flight planner: lawnmower grid generation and GSD/altitude calculations.

Ported from DSIdrone/templates/index.html serpentine grid logic.
All geometry uses WGS84 (lat/lng decimal degrees).
"""

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon, LineString, MultiLineString, Point


@dataclass
class CameraPreset:
    """DJI camera specifications for GSD/altitude calculations."""
    name: str
    sensor_width_mm: float     # Physical sensor width in mm
    image_width_px: int        # Image width in pixels
    min_focal_length_mm: float # Minimum focal length (no zoom)
    max_focal_length_mm: float # Maximum focal length (max zoom)
    # DJI WPML identifiers
    drone_enum_value: int
    drone_sub_enum_value: int = 1
    payload_enum_value: int = 0
    payload_position_index: int = 0
    payload_lens_index: str = "zoom"


# Presets from DSIdrone — tested with DJI Pilot 2
CAMERA_PRESETS = {
    "m30t": CameraPreset(
        name="DJI M30T",
        sensor_width_mm=7.68,
        image_width_px=640,
        min_focal_length_mm=9.1,
        max_focal_length_mm=147.0,
        drone_enum_value=67,
        payload_enum_value=53,
        payload_position_index=0,
        payload_lens_index="zoom",
    ),
    "m30t_wide": CameraPreset(
        name="DJI M30T (Wide)",
        sensor_width_mm=9.6,
        image_width_px=8000,
        min_focal_length_mm=4.48,
        max_focal_length_mm=4.48,
        drone_enum_value=67,
        payload_enum_value=53,
        payload_position_index=0,
        payload_lens_index="wide",
    ),
    "m30t_thermal": CameraPreset(
        name="DJI M30T (Thermal)",
        sensor_width_mm=7.68,  # IR sensor
        image_width_px=640,
        min_focal_length_mm=9.1,
        max_focal_length_mm=9.1,
        drone_enum_value=67,
        payload_enum_value=53,
        payload_position_index=0,
        payload_lens_index="ir",
    ),
    "mavic3e": CameraPreset(
        name="DJI Mavic 3E / M3E",
        sensor_width_mm=17.3,
        image_width_px=5472,
        min_focal_length_mm=24.0,
        max_focal_length_mm=162.0,
        drone_enum_value=77,
        payload_enum_value=69,
        payload_position_index=0,
        payload_lens_index="wide",
    ),
}


@dataclass
class WaypointGeo:
    """A waypoint with geographic coordinates and computed altitude."""
    latitude: float
    longitude: float
    altitude_agl: float = 0.0         # Relative to takeoff (AGL)
    altitude_absolute: float = 0.0    # WGS84 ellipsoid height
    terrain_elevation: float = 0.0    # Terrain elevation from DEM
    heading_deg: float = 0.0
    row_index: int = 0                # Which row this waypoint starts/ends


@dataclass
class FlightPlan:
    """Complete flight plan ready for KMZ export."""
    waypoints: list[WaypointGeo]
    altitude_agl: float               # Computed flight altitude AGL
    altitude_above_object: float      # Distance from camera to object
    gsd_cm_px: float                  # Computed GSD
    estimated_distance_m: float
    estimated_duration_s: float
    estimated_photos: int
    camera_preset: CameraPreset
    zoom_ratio: float
    photo_interval_s: float
    gimbal_pitch_deg: float
    flight_speed_ms: float


def calculate_altitude_from_gsd(
    gsd_cm_px: float,
    preset: CameraPreset,
    zoom_ratio: float = 1.0,
    object_height_m: float = 0.0,
) -> tuple[float, float]:
    """Calculate flight altitude from desired GSD.

    Formula from DSIdrone:
        altitude_above_object = (focal_length * image_width * GSD) / (sensor_width * 100)

    Args:
        gsd_cm_px: Desired ground sampling distance in cm/pixel.
        preset: Camera preset with sensor specs.
        zoom_ratio: Optical zoom multiplier (1.0 = no zoom).
        object_height_m: Height of object above ground (e.g., PV panels on trackers).

    Returns:
        (altitude_above_object_m, altitude_agl_m)
    """
    focal_length = preset.min_focal_length_mm * zoom_ratio
    focal_length = min(focal_length, preset.max_focal_length_mm)

    altitude_above_object = (
        focal_length * preset.image_width_px * gsd_cm_px
    ) / (preset.sensor_width_mm * 100)

    altitude_agl = altitude_above_object + object_height_m
    return altitude_above_object, altitude_agl


def _haversine_distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distance in meters between two WGS84 points."""
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _rotate_point(
    lat: float, lng: float, center_lat: float, center_lng: float, angle_rad: float
) -> tuple[float, float]:
    """Rotate a point around a center by angle_rad."""
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    tlat = lat - center_lat
    tlng = lng - center_lng
    rlat = tlng * sin_a + tlat * cos_a
    rlng = tlng * cos_a - tlat * sin_a
    return rlat + center_lat, rlng + center_lng


def generate_lawnmower_waypoints(
    boundary_coords: list[tuple[float, float]],
    num_rows: int,
    rotation_deg: float = 0.0,
    is_vertical: bool = True,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Generate serpentine (lawnmower) waypoints within a polygon boundary.

    Ported from DSIdrone calculateUnclippedRows + clipLineWithPolygon.

    Args:
        boundary_coords: List of (lat, lng) tuples defining the site boundary polygon.
        num_rows: Number of parallel flight lines.
        rotation_deg: Grid rotation in degrees (0 = aligned to bounding box).
        is_vertical: If True, prefer vertical lines; otherwise horizontal.

    Returns:
        List of line segments as ((lat1, lng1), (lat2, lng2)) in serpentine order.
    """
    if len(boundary_coords) < 3 or num_rows < 2:
        return []

    polygon = Polygon([(lng, lat) for lat, lng in boundary_coords])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    # Compute center
    center_lat = sum(c[0] for c in boundary_coords) / len(boundary_coords)
    center_lng = sum(c[1] for c in boundary_coords) / len(boundary_coords)
    angle_rad = math.radians(rotation_deg)

    # Rotate all boundary points to axis-aligned frame
    rotated = [
        _rotate_point(lat, lng, center_lat, center_lng, -angle_rad)
        for lat, lng in boundary_coords
    ]
    rot_lats = [p[0] for p in rotated]
    rot_lngs = [p[1] for p in rotated]

    min_lat, max_lat = min(rot_lats), max(rot_lats)
    min_lng, max_lng = min(rot_lngs), max(rot_lngs)
    lat_span = max_lat - min_lat
    lng_span = max_lng - min_lng

    # Decide whether to draw lines vertically or horizontally in rotated frame
    rotated_vertical_longer = lat_span > lng_span
    draw_vertical = (is_vertical and rotated_vertical_longer) or (
        not is_vertical and not rotated_vertical_longer
    )

    # Generate unclipped lines in rotated frame, then rotate back
    raw_lines = []
    for i in range(num_rows):
        step = i / (num_rows - 1) if num_rows > 1 else 0.5
        if draw_vertical:
            lng_pos = min_lng + lng_span * step
            p1 = (min_lat - lat_span * 1.5, lng_pos)
            p2 = (max_lat + lat_span * 1.5, lng_pos)
        else:
            lat_pos = min_lat + lat_span * step
            p1 = (lat_pos, min_lng - lng_span * 1.5)
            p2 = (lat_pos, max_lng + lng_span * 1.5)

        # Rotate back to original frame
        p1_orig = _rotate_point(p1[0], p1[1], center_lat, center_lng, angle_rad)
        p2_orig = _rotate_point(p2[0], p2[1], center_lat, center_lng, angle_rad)
        raw_lines.append((p1_orig, p2_orig))

    # Clip lines against polygon (slightly scaled to avoid edge misses)
    scaled_polygon = polygon.buffer(0.000001)
    clipped_lines = []
    for (lat1, lng1), (lat2, lng2) in raw_lines:
        line = LineString([(lng1, lat1), (lng2, lat2)])
        intersection = scaled_polygon.intersection(line)

        if intersection.is_empty:
            continue

        # Handle multi-line intersections (polygon with concave shapes)
        segments = []
        if isinstance(intersection, LineString):
            segments = [intersection]
        elif isinstance(intersection, MultiLineString):
            segments = list(intersection.geoms)

        for seg in segments:
            if seg.length > 0:
                coords = list(seg.coords)
                start = (coords[0][1], coords[0][0])   # (lat, lng)
                end = (coords[-1][1], coords[-1][0])
                clipped_lines.append((start, end))

    if not clipped_lines:
        return []

    # Create serpentine order (alternate direction each row)
    serpentine_segments = []
    for i, (start, end) in enumerate(clipped_lines):
        if i % 2 == 0:
            serpentine_segments.append((start, end))
        else:
            serpentine_segments.append((end, start))

    return serpentine_segments


def build_flight_plan(
    boundary_coords: list[tuple[float, float]],
    num_rows: int,
    gsd_cm_px: float,
    camera_preset_key: str = "m30t",
    rotation_deg: float = 0.0,
    is_vertical: bool = True,
    zoom_ratio: float = 1.0,
    object_height_m: float = 0.0,
    flight_speed_ms: float = 3.0,
    gimbal_pitch_deg: float = -90.0,
    photo_interval_s: float = 1.0,
    aircraft_yaw_deg: float = 0.0,
) -> FlightPlan:
    """Build a complete flight plan from site boundary and mission parameters.

    Args:
        boundary_coords: Site polygon as [(lat, lng), ...].
        num_rows: Number of parallel flight lines.
        gsd_cm_px: Desired ground sampling distance.
        camera_preset_key: Key in CAMERA_PRESETS dict.
        rotation_deg: Grid rotation degrees.
        is_vertical: Vertical or horizontal grid lines.
        zoom_ratio: Camera zoom multiplier.
        object_height_m: Object height above ground.
        flight_speed_ms: Flight speed in m/s.
        gimbal_pitch_deg: Gimbal pitch (-90 = nadir).
        photo_interval_s: Time between photos in seconds.
        aircraft_yaw_deg: Aircraft heading (0=North).

    Returns:
        FlightPlan with waypoints and computed parameters.
    """
    preset = CAMERA_PRESETS.get(camera_preset_key)
    if not preset:
        raise ValueError(f"Unknown camera preset: {camera_preset_key}")

    altitude_above_object, altitude_agl = calculate_altitude_from_gsd(
        gsd_cm_px, preset, zoom_ratio, object_height_m
    )

    segments = generate_lawnmower_waypoints(
        boundary_coords, num_rows, rotation_deg, is_vertical
    )

    # Convert segments to flat waypoint list
    waypoints = []
    for row_idx, (start, end) in enumerate(segments):
        waypoints.append(
            WaypointGeo(
                latitude=start[0],
                longitude=start[1],
                altitude_agl=altitude_agl,
                heading_deg=aircraft_yaw_deg,
                row_index=row_idx,
            )
        )
        waypoints.append(
            WaypointGeo(
                latitude=end[0],
                longitude=end[1],
                altitude_agl=altitude_agl,
                heading_deg=aircraft_yaw_deg,
                row_index=row_idx,
            )
        )

    # Compute estimated distance
    total_distance = 0.0
    for i in range(len(waypoints) - 1):
        total_distance += _haversine_distance(
            waypoints[i].latitude,
            waypoints[i].longitude,
            waypoints[i + 1].latitude,
            waypoints[i + 1].longitude,
        )

    duration = total_distance / flight_speed_ms if flight_speed_ms > 0 else 0
    estimated_photos = int(duration / photo_interval_s) if photo_interval_s > 0 else 0

    return FlightPlan(
        waypoints=waypoints,
        altitude_agl=altitude_agl,
        altitude_above_object=altitude_above_object,
        gsd_cm_px=gsd_cm_px,
        estimated_distance_m=total_distance,
        estimated_duration_s=duration,
        estimated_photos=estimated_photos,
        camera_preset=preset,
        zoom_ratio=zoom_ratio,
        photo_interval_s=photo_interval_s,
        gimbal_pitch_deg=gimbal_pitch_deg,
        flight_speed_ms=flight_speed_ms,
    )
