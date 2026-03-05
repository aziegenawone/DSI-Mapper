"""Panel row detection from satellite/aerial imagery.

Detects solar panel rows (filari) in satellite imagery and generates
flight waypoints along each detected row centerline.

Improved from DSIdrone approach with:
- Better preprocessing (adaptive thresholding, morphological operations)
- CLAHE contrast enhancement for variable-quality satellite imagery
- Line segment clustering (group parallel segments into rows)
- Row ordering (sort by perpendicular distance for serpentine flight path)
- Proper coordinate projection via bilinear interpolation on WGS84 bounds
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import cv2

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class MapBounds:
    """Geographic bounds of an image (WGS84 decimal degrees)."""
    north: float
    south: float
    east: float
    west: float

    def __post_init__(self) -> None:
        if self.north <= self.south:
            raise ValueError(
                f"MapBounds: north ({self.north}) must be greater than south ({self.south})"
            )
        if self.east <= self.west:
            raise ValueError(
                f"MapBounds: east ({self.east}) must be greater than west ({self.west})"
            )

    @property
    def lat_span(self) -> float:
        return self.north - self.south

    @property
    def lng_span(self) -> float:
        return self.east - self.west

    @property
    def center_lat(self) -> float:
        return (self.north + self.south) / 2.0

    @property
    def center_lng(self) -> float:
        return (self.east + self.west) / 2.0


@dataclass
class DetectedRow:
    """A detected solar panel row with geographic coordinates."""
    row_index: int
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    angle_deg: float   # Row orientation angle in degrees [0, 180)
    length_m: float    # Approximate length in meters (haversine)
    confidence: float  # Detection confidence [0, 1]

    def as_segment(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return row as ((start_lat, start_lng), (end_lat, end_lng))."""
        return (self.start_lat, self.start_lng), (self.end_lat, self.end_lng)


# ---------------------------------------------------------------------------
# Coordinate conversion utilities
# ---------------------------------------------------------------------------


def pixel_to_geo(
    px: int,
    py: int,
    bounds: MapBounds,
    img_width: int,
    img_height: int,
) -> tuple[float, float]:
    """Convert pixel coordinates to geographic (lat, lng).

    Pixel (0, 0) is top-left (north-west corner).
    Pixel (img_width-1, img_height-1) is bottom-right (south-east corner).

    Args:
        px: Pixel x coordinate (column, increases eastward).
        py: Pixel y coordinate (row, increases southward).
        bounds: Geographic bounds of the image.
        img_width: Image width in pixels.
        img_height: Image height in pixels.

    Returns:
        (latitude, longitude) in decimal degrees.
    """
    if img_width <= 0 or img_height <= 0:
        raise ValueError("Image dimensions must be positive")

    lng = bounds.west + (px / img_width) * bounds.lng_span
    lat = bounds.north - (py / img_height) * bounds.lat_span
    return lat, lng


def geo_to_pixel(
    lat: float,
    lng: float,
    bounds: MapBounds,
    img_width: int,
    img_height: int,
) -> tuple[int, int]:
    """Convert geographic (lat, lng) to pixel coordinates.

    Args:
        lat: Latitude in decimal degrees.
        lng: Longitude in decimal degrees.
        bounds: Geographic bounds of the image.
        img_width: Image width in pixels.
        img_height: Image height in pixels.

    Returns:
        (px, py) pixel coordinates (clamped to image bounds).
    """
    if img_width <= 0 or img_height <= 0:
        raise ValueError("Image dimensions must be positive")

    px = int((lng - bounds.west) / bounds.lng_span * img_width)
    py = int((bounds.north - lat) / bounds.lat_span * img_height)
    px = max(0, min(img_width - 1, px))
    py = max(0, min(img_height - 1, py))
    return px, py


def _haversine_distance(
    lat1: float, lng1: float, lat2: float, lng2: float
) -> float:
    """Distance in meters between two WGS84 points (haversine formula)."""
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _meters_per_pixel(bounds: MapBounds, img_width: int, img_height: int) -> float:
    """Estimate meters per pixel using the image horizontal span."""
    center_lat = bounds.center_lat
    west_m = 0.0
    east_m = _haversine_distance(center_lat, bounds.west, center_lat, bounds.east)
    return east_m / img_width if img_width > 0 else 1.0


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------


def _apply_polygon_mask(
    image: np.ndarray,
    polygon_coords: list[tuple[float, float]],
    bounds: MapBounds,
) -> np.ndarray:
    """Apply a geographic polygon mask to the image.

    Pixels outside the polygon are set to black (0).

    Args:
        image: Input image array (H, W) or (H, W, C).
        polygon_coords: List of (lat, lng) defining the mask polygon.
        bounds: Geographic bounds of the image.

    Returns:
        Masked image with same shape and dtype as input.
    """
    h, w = image.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    pixel_pts = np.array(
        [geo_to_pixel(lat, lng, bounds, w, h) for lat, lng in polygon_coords],
        dtype=np.int32,
    )
    cv2.fillPoly(mask, [pixel_pts], 255)
    if image.ndim == 3:
        mask_3c = cv2.merge([mask, mask, mask])
        return cv2.bitwise_and(image, mask_3c)
    return cv2.bitwise_and(image, image, mask=mask)


def _preprocess_for_detection(gray: np.ndarray) -> np.ndarray:
    """Preprocess a grayscale image for line detection.

    Steps:
    1. CLAHE (Contrast Limited Adaptive Histogram Equalization) — improves
       contrast in locally dark/bright regions typical of satellite imagery.
    2. Gaussian blur to suppress high-frequency noise before edge detection.
    3. Morphological closing to bridge small gaps in panel edges (kernel
       oriented both horizontally and at 45° to cover rotated panels).

    Args:
        gray: Grayscale image (H, W), uint8.

    Returns:
        Preprocessed image ready for Canny edge detection.
    """
    # CLAHE with moderate clip limit — too aggressive creates phantom edges
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Mild Gaussian blur — σ≈1 px preserves edges while reducing speckle
    blurred = cv2.GaussianBlur(enhanced, (3, 3), 0)

    # Morphological closing: close small intra-panel gaps.
    # Horizontal kernel captures row-parallel gaps.
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 1))
    closed = cv2.morphologyEx(blurred, cv2.MORPH_CLOSE, h_kernel)

    return closed


# ---------------------------------------------------------------------------
# Line detection and clustering
# ---------------------------------------------------------------------------


def _detect_lines_hough(
    preprocessed: np.ndarray,
    min_line_length_px: int,
) -> np.ndarray | None:
    """Run Canny + HoughLinesP on a preprocessed grayscale image.

    Uses adaptive Canny thresholds based on image median intensity to
    handle variable-quality satellite imagery.

    Args:
        preprocessed: Preprocessed grayscale image.
        min_line_length_px: Minimum line length in pixels to accept.

    Returns:
        Array of shape (N, 1, 4) with [x1, y1, x2, y2] or None if no lines.
    """
    # Adaptive Canny thresholds: sigma method (Otsu-like)
    median_val = float(np.median(preprocessed))
    sigma = 0.33
    low = max(0, int((1.0 - sigma) * median_val))
    high = min(255, int((1.0 + sigma) * median_val))
    # Ensure a minimum contrast range
    if high - low < 30:
        low = max(0, low - 15)
        high = min(255, high + 15)

    edges = cv2.Canny(preprocessed, low, high, apertureSize=3)

    # HoughLinesP: probabilistic Hough — more robust than standard Hough
    # for images with discontinuous or cluttered edges.
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=math.pi / 180,
        threshold=max(15, min_line_length_px // 3),
        minLineLength=min_line_length_px,
        maxLineGap=min_line_length_px // 2,
    )
    return lines


def _line_angle_deg(x1: int, y1: int, x2: int, y2: int) -> float:
    """Return line angle in [0, 180) degrees."""
    angle = math.degrees(math.atan2(float(y2 - y1), float(x2 - x1))) % 180
    return angle


def _perpendicular_distance(
    px: float, py: float,
    x1: float, y1: float, x2: float, y2: float,
) -> float:
    """Perpendicular distance from point (px,py) to line through (x1,y1)-(x2,y2)."""
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return math.hypot(px - x1, py - y1)
    return abs(dy * px - dx * py + x2 * y1 - y2 * x1) / length


def _angle_difference(a1: float, a2: float) -> float:
    """Smallest angular difference between two angles in [0, 180) degrees."""
    diff = abs(a1 - a2) % 180
    return min(diff, 180 - diff)


def _cluster_parallel_lines(
    lines: np.ndarray,
    angle_tolerance_deg: float = 10.0,
    distance_tolerance_px: float = 20.0,
) -> list[list[tuple[int, int, int, int]]]:
    """Group Hough line segments into clusters of parallel, co-linear lines.

    Two segments are merged into the same cluster if:
    - Their orientations differ by less than `angle_tolerance_deg`, AND
    - The perpendicular distance between their midpoints is less than
      `distance_tolerance_px`.

    This is a greedy single-linkage clustering (O(N²)) — acceptable for the
    typical number of Hough lines returned per image (<1000).

    Args:
        lines: Array of shape (N, 1, 4) from HoughLinesP.
        angle_tolerance_deg: Max angle difference to consider parallel.
        distance_tolerance_px: Max perpendicular distance to merge segments.

    Returns:
        List of clusters, each cluster is a list of (x1, y1, x2, y2).
    """
    segments: list[tuple[int, int, int, int]] = [
        (int(l[0][0]), int(l[0][1]), int(l[0][2]), int(l[0][3]))
        for l in lines
    ]

    if not segments:
        return []

    # Precompute angles and midpoints
    angles = [_line_angle_deg(*s) for s in segments]
    midpoints = [
        ((s[0] + s[2]) / 2.0, (s[1] + s[3]) / 2.0) for s in segments
    ]

    n = len(segments)
    cluster_ids = list(range(n))  # initially each segment is its own cluster

    def find(i: int) -> int:
        while cluster_ids[i] != i:
            cluster_ids[i] = cluster_ids[cluster_ids[i]]
            i = cluster_ids[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            cluster_ids[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _angle_difference(angles[i], angles[j]) > angle_tolerance_deg:
                continue
            mx, my = midpoints[i]
            x1, y1, x2, y2 = segments[j]
            dist = _perpendicular_distance(mx, my, x1, y1, x2, y2)
            if dist <= distance_tolerance_px:
                union(i, j)

    # Collect segments by root
    from collections import defaultdict
    clusters_dict: dict[int, list[tuple[int, int, int, int]]] = defaultdict(list)
    for i in range(n):
        clusters_dict[find(i)].append(segments[i])

    return list(clusters_dict.values())


def _merge_cluster_to_centerline(
    cluster: list[tuple[int, int, int, int]],
) -> tuple[float, float, float, float, float]:
    """Merge a cluster of co-linear segments into a single representative line.

    Strategy:
    1. Compute a weighted-average angle (weight by segment length).
    2. Project all endpoints onto the dominant direction vector.
    3. Take the min/max projection to get the overall span of the row.

    Returns:
        (x1, y1, x2, y2, angle_deg) — the merged centerline endpoints.
    """
    # Weighted average angle
    angles = [_line_angle_deg(*s) for s in cluster]
    lengths = [math.hypot(s[2] - s[0], s[3] - s[1]) for s in cluster]
    total_len = sum(lengths) or 1.0

    # Handle angle wrapping: convert to unit vectors, average, then back
    sin_sum = sum(math.sin(2 * math.radians(a)) * w for a, w in zip(angles, lengths))
    cos_sum = sum(math.cos(2 * math.radians(a)) * w for a, w in zip(angles, lengths))
    avg_angle = math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0 % 180

    # Direction vector for the dominant angle
    dx = math.cos(math.radians(avg_angle))
    dy = math.sin(math.radians(avg_angle))

    # Centroid of all midpoints (weighted by length)
    cx = sum((s[0] + s[2]) / 2.0 * w for s, w in zip(cluster, lengths)) / total_len
    cy = sum((s[1] + s[3]) / 2.0 * w for s, w in zip(cluster, lengths)) / total_len

    # Project all endpoints onto the direction vector through (cx, cy)
    projections: list[float] = []
    for x1, y1, x2, y2 in cluster:
        projections.append((x1 - cx) * dx + (y1 - cy) * dy)
        projections.append((x2 - cx) * dx + (y2 - cy) * dy)

    t_min = min(projections)
    t_max = max(projections)

    mx1 = cx + t_min * dx
    my1 = cy + t_min * dy
    mx2 = cx + t_max * dx
    my2 = cy + t_max * dy

    return mx1, my1, mx2, my2, avg_angle


# ---------------------------------------------------------------------------
# Row sorting
# ---------------------------------------------------------------------------


def _perp_offset_for_sort(
    cl: tuple[float, float, float, float, float],
    dominant_angle: float | None = None,
) -> float:
    """Compute the perpendicular offset of a centerline for sorting.

    Args:
        cl: (x1, y1, x2, y2, angle_deg) centerline tuple.
        dominant_angle: Override for the dominant angle (degrees).
                        If None, uses the centerline's own angle.

    Returns:
        Scalar perpendicular offset (larger = further in the sort direction).
    """
    angle = dominant_angle if dominant_angle is not None else cl[4]
    perp_angle = angle + 90.0
    perp_dx = math.cos(math.radians(perp_angle))
    perp_dy = math.sin(math.radians(perp_angle))
    mx = (cl[0] + cl[2]) / 2.0
    my = (cl[1] + cl[3]) / 2.0
    return mx * perp_dx + my * perp_dy


def _sort_rows_for_serpentine(
    centerlines: list[tuple[float, float, float, float, float]],
) -> list[tuple[float, float, float, float, float]]:
    """Sort row centerlines by perpendicular distance from a reference line.

    Finds the dominant direction (median angle of all segments), then sorts
    all rows by their offset perpendicular to that direction.  This gives a
    consistent top-to-bottom or left-to-right ordering that produces a
    valid serpentine flight path.

    Args:
        centerlines: List of (x1, y1, x2, y2, angle_deg).

    Returns:
        Sorted list of centerlines.
    """
    if not centerlines:
        return []

    # Use the median angle to define the dominant row direction
    dominant_angle = float(np.median([c[4] for c in centerlines]))

    return sorted(
        centerlines,
        key=lambda cl: _perp_offset_for_sort(cl, dominant_angle),
    )


# ---------------------------------------------------------------------------
# Main detection function
# ---------------------------------------------------------------------------


def detect_panel_rows(
    image: np.ndarray,
    bounds: MapBounds,
    polygon_coords: Optional[list[tuple[float, float]]] = None,
    min_row_length_px: int = 50,
    min_aspect_ratio: float = 3.0,
    angle_tolerance_deg: float = 10.0,
    distance_tolerance_px: float = 25.0,
) -> list[DetectedRow]:
    """Detect solar panel rows in satellite/aerial imagery.

    Pipeline:
    1.  Validate inputs.
    2.  Apply polygon mask if provided.
    3.  Convert to grayscale.
    4.  CLAHE contrast enhancement.
    5.  Gaussian blur + morphological closing.
    6.  Adaptive Canny edge detection.
    7.  Probabilistic Hough line detection (HoughLinesP).
    8.  Filter by minimum length and aspect ratio.
    9.  Cluster parallel segments into row groups.
    10. Merge each cluster into a single centerline.
    11. Sort rows by perpendicular offset (serpentine ordering).
    12. Convert pixel centerlines to geographic coordinates.

    Args:
        image: Input image as numpy array (H, W, C) BGR or (H, W) grayscale.
               uint8.
        bounds: Geographic bounds of the image.
        polygon_coords: Optional list of (lat, lng) tuples defining a mask
                        polygon.  Only pixels inside the polygon are analysed.
        min_row_length_px: Minimum detected row length in pixels.  Segments
                           shorter than this are discarded before clustering.
        min_aspect_ratio: Minimum length/width ratio for contour-based
                          pre-filtering.  Applied after Hough to remove blobs.
        angle_tolerance_deg: Max angle difference between two segments to be
                             considered parallel (clustering parameter).
        distance_tolerance_px: Max perpendicular distance between parallel
                                segments to be merged into the same row.

    Returns:
        List of DetectedRow objects sorted for a serpentine flight path.
        Returns an empty list if no rows are detected.

    Raises:
        ValueError: If the image is None, empty, or has an invalid shape.
    """
    # --- Input validation ---
    if image is None or image.size == 0:
        raise ValueError("Image is None or empty")
    if image.ndim not in (2, 3):
        raise ValueError(f"Image must be 2D or 3D, got ndim={image.ndim}")
    if image.dtype != np.uint8:
        # Normalise to uint8
        img_min, img_max = float(image.min()), float(image.max())
        if img_max > img_min:
            image = ((image - img_min) / (img_max - img_min) * 255).astype(np.uint8)
        else:
            image = np.zeros_like(image, dtype=np.uint8)

    h, w = image.shape[:2]
    if h < 10 or w < 10:
        raise ValueError(f"Image too small: {w}x{h}")

    # --- Step 1: polygon mask ---
    if polygon_coords and len(polygon_coords) >= 3:
        try:
            image = _apply_polygon_mask(image, polygon_coords, bounds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Polygon mask failed (%s), proceeding without mask", exc)

    # --- Step 2: grayscale conversion ---
    if image.ndim == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # --- Steps 3–5: preprocessing ---
    preprocessed = _preprocess_for_detection(gray)

    # --- Steps 6–7: Hough line detection ---
    lines = _detect_lines_hough(preprocessed, min_row_length_px)
    if lines is None or len(lines) == 0:
        logger.debug("No Hough lines detected in image")
        return []

    logger.debug("HoughLinesP detected %d raw line segments", len(lines))

    # --- Step 8: filter by length and aspect ratio ---
    filtered: list[tuple[int, int, int, int]] = []
    for line in lines:
        x1, y1, x2, y2 = int(line[0][0]), int(line[0][1]), int(line[0][2]), int(line[0][3])
        length = math.hypot(x2 - x1, y2 - y1)
        if length < min_row_length_px:
            continue
        # Approximate aspect ratio using bounding box
        bw = max(abs(x2 - x1), 1)
        bh = max(abs(y2 - y1), 1)
        aspect = max(bw, bh) / min(bw, bh)
        if aspect < min_aspect_ratio:
            continue
        filtered.append((x1, y1, x2, y2))

    if not filtered:
        logger.debug("No segments pass length/aspect filter")
        return []

    logger.debug("%d segments after length/aspect filter", len(filtered))

    # --- Step 9: cluster parallel segments ---
    # Rebuild a minimal lines array for the cluster function
    lines_arr = np.array([[[x1, y1, x2, y2]] for x1, y1, x2, y2 in filtered], dtype=np.int32)
    clusters = _cluster_parallel_lines(
        lines_arr,
        angle_tolerance_deg=angle_tolerance_deg,
        distance_tolerance_px=distance_tolerance_px,
    )

    logger.debug("Formed %d clusters from %d segments", len(clusters), len(filtered))

    # --- Step 10: merge each cluster into a centerline ---
    # Each entry: (x1, y1, x2, y2, angle_deg, confidence).
    # Confidence is computed here while we still have the cluster size,
    # before sorting shuffles the correspondence.
    centerlines: list[tuple[float, float, float, float, float, float]] = []
    for cluster in clusters:
        if not cluster:
            continue
        cl = _merge_cluster_to_centerline(cluster)
        # Discard degenerate centerlines
        if math.hypot(cl[2] - cl[0], cl[3] - cl[1]) < min_row_length_px:
            continue
        # Confidence: proxy based on cluster size (number of merged segments).
        # Normalise to [0.1, 1.0] — even a single-segment row gets 0.1.
        cluster_size = len(cluster)
        confidence = min(1.0, 0.1 + 0.9 * min(cluster_size, 10) / 10.0)
        centerlines.append((cl[0], cl[1], cl[2], cl[3], cl[4], confidence))

    if not centerlines:
        return []

    # --- Step 11: sort for serpentine path ---
    # Use the median angle of all centerlines as the dominant direction so
    # every row is projected onto the same perpendicular axis.
    dominant_angle = float(np.median([c[4] for c in centerlines]))
    centerlines = sorted(
        centerlines,
        key=lambda c: _perp_offset_for_sort((c[0], c[1], c[2], c[3], c[4]), dominant_angle),
    )

    # --- Step 12: convert to geographic coordinates ---
    mpp = _meters_per_pixel(bounds, w, h)
    rows: list[DetectedRow] = []

    for idx, (x1, y1, x2, y2, angle_deg, confidence) in enumerate(centerlines):
        start_lat, start_lng = pixel_to_geo(int(round(x1)), int(round(y1)), bounds, w, h)
        end_lat, end_lng = pixel_to_geo(int(round(x2)), int(round(y2)), bounds, w, h)

        # Length estimate: pixel length * meters-per-pixel
        px_length = math.hypot(x2 - x1, y2 - y1)
        length_m = px_length * mpp

        rows.append(
            DetectedRow(
                row_index=idx,
                start_lat=start_lat,
                start_lng=start_lng,
                end_lat=end_lat,
                end_lng=end_lng,
                angle_deg=angle_deg % 180,
                length_m=length_m,
                confidence=confidence,
            )
        )

    logger.info("Detected %d panel rows", len(rows))
    return rows


# ---------------------------------------------------------------------------
# Waypoint generation
# ---------------------------------------------------------------------------


def generate_row_following_waypoints(
    rows: list[DetectedRow],
    altitude_agl: float,
    margin_m: float = 5.0,
    heading_deg: float = 0.0,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Generate flight waypoints that follow each detected row.

    Creates a serpentine path that flies along each row centerline.
    Adds a geographic margin at the start/end of each row for
    drone acceleration/deceleration room.

    The direction of travel alternates each row (serpentine): even-indexed
    rows fly start→end; odd-indexed rows fly end→start.

    Args:
        rows: Detected rows, already sorted for a serpentine path.
        altitude_agl: Flight altitude above ground level in metres.
        margin_m: Extra distance (metres) added beyond each row endpoint to
                  allow the drone to stabilise before/after photo capture.
        heading_deg: Aircraft heading override (degrees, 0 = North).

    Returns:
        List of ((start_lat, start_lng), (end_lat, end_lng)) segments in
        serpentine order.  Each segment corresponds to one row pass.

    Notes:
        - If `rows` is empty, returns an empty list.
        - altitude_agl must be positive; if not, a ValueError is raised.
    """
    if altitude_agl <= 0:
        raise ValueError(f"altitude_agl must be positive, got {altitude_agl}")

    if not rows:
        return []

    segments: list[tuple[tuple[float, float], tuple[float, float]]] = []

    for i, row in enumerate(rows):
        slat, slng = row.start_lat, row.start_lng
        elat, elng = row.end_lat, row.end_lng

        # Compute bearing from start to end to project margins along the row
        dlat = math.radians(elat - slat)
        dlng = math.radians(elng - slng)
        bearing = math.atan2(dlng, dlat)  # simplified bearing in radians

        # Convert margin_m to degrees (approximate, assumes small angles)
        # Use the average latitude for the lng degree conversion
        avg_lat = (slat + elat) / 2.0
        lat_deg_per_m = 1.0 / 111_320.0
        lng_deg_per_m = 1.0 / (111_320.0 * math.cos(math.radians(avg_lat)))
        # Guard against polar lat_deg issues (not a concern for PV plants)
        lng_deg_per_m = max(lng_deg_per_m, 1e-10)

        margin_lat = margin_m * lat_deg_per_m * math.cos(bearing)
        margin_lng = margin_m * lng_deg_per_m * math.sin(bearing)

        # Extend endpoints by margin
        ext_start = (slat - margin_lat, slng - margin_lng)
        ext_end = (elat + margin_lat, elng + margin_lng)

        # Alternate direction for serpentine
        if i % 2 == 0:
            segments.append((ext_start, ext_end))
        else:
            segments.append((ext_end, ext_start))

    return segments
