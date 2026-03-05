"""Panel row detection endpoint.

Accepts a satellite/aerial image upload together with its geographic
bounds and an optional site-boundary polygon.  Returns the detected
panel row centerlines and optionally generates flight waypoints along
each row for a serpentine inspection flight.
"""

import json
import logging

import cv2
import numpy as np
from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.services.row_detector import (
    DetectedRow,
    MapBounds,
    detect_panel_rows,
    generate_row_following_waypoints,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Supported image MIME types
# ---------------------------------------------------------------------------

_ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/tiff",
    "image/webp",
}

_MAX_IMAGE_BYTES = 50 * 1024 * 1024  # 50 MB hard limit


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class DetectedRowResponse(BaseModel):
    """Serialized representation of a single detected row."""
    row_index: int
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    angle_deg: float
    length_m: float
    confidence: float


class WaypointSegmentResponse(BaseModel):
    """A flight waypoint segment (start + end of one row pass)."""
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    row_index: int


class RowDetectionResponse(BaseModel):
    """Full response from the /detect-rows endpoint."""
    detected_rows: list[DetectedRowResponse]
    waypoints: list[WaypointSegmentResponse]
    num_rows_detected: int
    image_width_px: int
    image_height_px: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_response(row: DetectedRow) -> DetectedRowResponse:
    return DetectedRowResponse(
        row_index=row.row_index,
        start_lat=row.start_lat,
        start_lng=row.start_lng,
        end_lat=row.end_lat,
        end_lng=row.end_lng,
        angle_deg=row.angle_deg,
        length_m=round(row.length_m, 2),
        confidence=round(row.confidence, 4),
    )


def _parse_polygon_coords(polygon_coords_json: str | None) -> list[tuple[float, float]] | None:
    """Parse polygon_coords from a JSON string into a list of (lat, lng) tuples.

    Expected format: "[[lat1, lng1], [lat2, lng2], ...]"

    Returns None if the input is None or an empty string.

    Raises:
        HTTPException 400: If the JSON is malformed or coordinates are invalid.
    """
    if not polygon_coords_json:
        return None

    try:
        raw = json.loads(polygon_coords_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"polygon_coords is not valid JSON: {exc}",
        ) from exc

    if not isinstance(raw, list):
        raise HTTPException(
            status_code=400,
            detail="polygon_coords must be a JSON array of [lat, lng] pairs",
        )

    coords: list[tuple[float, float]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise HTTPException(
                status_code=400,
                detail=f"polygon_coords[{i}] must be [lat, lng], got {item!r}",
            )
        try:
            lat, lng = float(item[0]), float(item[1])
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"polygon_coords[{i}] contains non-numeric values: {exc}",
            ) from exc
        if not (-90 <= lat <= 90):
            raise HTTPException(
                status_code=400,
                detail=f"polygon_coords[{i}] latitude {lat} is out of range [-90, 90]",
            )
        if not (-180 <= lng <= 180):
            raise HTTPException(
                status_code=400,
                detail=f"polygon_coords[{i}] longitude {lng} is out of range [-180, 180]",
            )
        coords.append((lat, lng))

    if len(coords) < 3:
        raise HTTPException(
            status_code=400,
            detail="polygon_coords must contain at least 3 coordinate pairs to form a polygon",
        )

    return coords


async def _read_image_bytes(upload: UploadFile) -> bytes:
    """Read and validate the uploaded image.

    Raises:
        HTTPException 400: If the file is missing, too large, or has an
                           unsupported content type.
    """
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported image type '{content_type}'. "
                f"Allowed: {', '.join(sorted(_ALLOWED_CONTENT_TYPES))}"
            ),
        )

    data = await upload.read()
    if len(data) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(data) > _MAX_IMAGE_BYTES:
        mb = len(data) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"Image too large ({mb:.1f} MB). Maximum allowed: 50 MB",
        )
    return data


def _decode_image(data: bytes) -> np.ndarray:
    """Decode raw image bytes to a numpy array (BGR uint8).

    Raises:
        HTTPException 422: If the bytes cannot be decoded as an image.
    """
    arr = np.frombuffer(data, dtype=np.uint8)
    img = None
    try:
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail=f"Failed to decode image: {exc}",
        ) from exc

    if img is None:
        raise HTTPException(
            status_code=422,
            detail="Could not decode image. Ensure the file is a valid JPEG/PNG/TIFF/WebP.",
        )
    return img


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/detect-rows", response_model=RowDetectionResponse)
async def detect_rows(
    image: UploadFile,
    bounds_north: float = Form(..., description="Northern latitude bound (WGS84)"),
    bounds_south: float = Form(..., description="Southern latitude bound (WGS84)"),
    bounds_east: float = Form(..., description="Eastern longitude bound (WGS84)"),
    bounds_west: float = Form(..., description="Western longitude bound (WGS84)"),
    polygon_coords: str | None = Form(
        None,
        description='Optional site boundary as JSON string: [[lat,lng], ...]',
    ),
    min_row_length_px: int = Form(
        50,
        ge=10,
        le=2000,
        description="Minimum row length in pixels to detect",
    ),
    min_aspect_ratio: float = Form(
        3.0,
        ge=1.5,
        le=20.0,
        description="Minimum length-to-width aspect ratio for a valid row",
    ),
    altitude_agl: float = Form(
        30.0,
        ge=1.0,
        le=500.0,
        description="Flight altitude AGL in metres for waypoint generation",
    ),
    margin_m: float = Form(
        5.0,
        ge=0.0,
        le=100.0,
        description="Margin in metres added beyond each row endpoint",
    ),
    heading_deg: float = Form(
        0.0,
        ge=0.0,
        lt=360.0,
        description="Aircraft heading for waypoints (0 = North)",
    ),
):
    """Detect panel rows from an uploaded satellite/aerial image.

    Accepts a multipart/form-data request containing:
    - **image**: The satellite or aerial image file (JPEG, PNG, TIFF, or WebP).
    - **bounds_north/south/east/west**: WGS84 geographic bounds of the image.
    - **polygon_coords** *(optional)*: JSON array ``[[lat,lng], ...]`` defining
      a mask polygon.  Only pixels inside the polygon are analysed.
    - **min_row_length_px**: Minimum row length threshold (default 50 px).
    - **min_aspect_ratio**: Minimum aspect ratio filter (default 3.0).
    - **altitude_agl**: Flight altitude for the generated waypoints (default 30 m).
    - **margin_m**: Extension beyond each row endpoint (default 5 m).
    - **heading_deg**: Aircraft heading for waypoints (default 0° = North).

    Returns detected rows and a serpentine waypoint plan.
    """
    # --- Validate bounds ---
    try:
        bounds = MapBounds(
            north=bounds_north,
            south=bounds_south,
            east=bounds_east,
            west=bounds_west,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- Parse optional polygon ---
    poly = _parse_polygon_coords(polygon_coords)

    # --- Read and decode image ---
    image_bytes = await _read_image_bytes(image)
    img_array = _decode_image(image_bytes)
    img_h, img_w = img_array.shape[:2]

    logger.info(
        "detect_rows: image %dx%d, bounds N=%.6f S=%.6f E=%.6f W=%.6f, poly=%s",
        img_w, img_h,
        bounds_north, bounds_south, bounds_east, bounds_west,
        f"{len(poly)} pts" if poly else "none",
    )

    # --- Run detection ---
    try:
        rows = detect_panel_rows(
            image=img_array,
            bounds=bounds,
            polygon_coords=poly,
            min_row_length_px=min_row_length_px,
            min_aspect_ratio=min_aspect_ratio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in detect_panel_rows")
        raise HTTPException(
            status_code=500,
            detail=f"Row detection failed: {exc}",
        ) from exc

    # --- Generate waypoints ---
    try:
        wp_segments = generate_row_following_waypoints(
            rows=rows,
            altitude_agl=altitude_agl,
            margin_m=margin_m,
            heading_deg=heading_deg,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    waypoints = [
        WaypointSegmentResponse(
            start_lat=start[0],
            start_lng=start[1],
            end_lat=end[0],
            end_lng=end[1],
            row_index=i,
        )
        for i, (start, end) in enumerate(wp_segments)
    ]

    return RowDetectionResponse(
        detected_rows=[_row_to_response(r) for r in rows],
        waypoints=waypoints,
        num_rows_detected=len(rows),
        image_width_px=img_w,
        image_height_px=img_h,
    )
