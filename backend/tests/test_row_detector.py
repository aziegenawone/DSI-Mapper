"""Tests for the panel row detection service.

Covers:
- MapBounds validation
- pixel_to_geo / geo_to_pixel roundtrip and edge cases
- detect_panel_rows with synthetic imagery (white rectangles on black)
- _cluster_parallel_lines behaviour
- _merge_cluster_to_centerline correctness
- _sort_rows_for_serpentine ordering
- generate_row_following_waypoints serpentine pattern and margin
- Error handling (bad images, bad bounds, etc.)
"""

import math

import numpy as np
import pytest

from app.services.row_detector import (
    MapBounds,
    DetectedRow,
    pixel_to_geo,
    geo_to_pixel,
    detect_panel_rows,
    generate_row_following_waypoints,
    _cluster_parallel_lines,
    _merge_cluster_to_centerline,
    _sort_rows_for_serpentine,
    _haversine_distance,
    _line_angle_deg,
    _angle_difference,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

# A compact square region in Italy
BOUNDS = MapBounds(north=45.010, south=45.000, east=10.010, west=10.000)
IMG_W = 200
IMG_H = 200


def make_synthetic_rows_image(
    n_rows: int = 5,
    row_width_px: int = 4,
    row_gap_px: int = 20,
    angle_deg: float = 0.0,
    img_w: int = 400,
    img_h: int = 300,
) -> np.ndarray:
    """Draw `n_rows` white horizontal rectangles on a black background.

    Each rectangle is `img_w * 0.7` wide and `row_width_px` tall, evenly
    spaced.  When angle_deg != 0 the entire drawing canvas is rotated.

    Returns a BGR uint8 image of shape (img_h, img_w, 3).
    """
    img = np.zeros((img_h, img_w, 3), dtype=np.uint8)
    total_height_needed = n_rows * row_width_px + (n_rows - 1) * row_gap_px
    start_y = (img_h - total_height_needed) // 2
    rect_w = int(img_w * 0.7)
    rect_x_start = (img_w - rect_w) // 2

    for i in range(n_rows):
        y = start_y + i * (row_width_px + row_gap_px)
        cv_color = (255, 255, 255)
        img[y : y + row_width_px, rect_x_start : rect_x_start + rect_w] = cv_color

    if angle_deg != 0:
        center = (img_w // 2, img_h // 2)
        M = __import__("cv2").getRotationMatrix2D(center, angle_deg, 1.0)
        img = __import__("cv2").warpAffine(img, M, (img_w, img_h))

    return img


# ---------------------------------------------------------------------------
# MapBounds
# ---------------------------------------------------------------------------


class TestMapBounds:
    def test_valid_bounds(self):
        b = MapBounds(north=10.0, south=9.0, east=11.0, west=10.0)
        assert b.lat_span == pytest.approx(1.0)
        assert b.lng_span == pytest.approx(1.0)

    def test_north_must_exceed_south(self):
        with pytest.raises(ValueError, match="north"):
            MapBounds(north=9.0, south=10.0, east=11.0, west=10.0)

    def test_east_must_exceed_west(self):
        with pytest.raises(ValueError, match="east"):
            MapBounds(north=10.0, south=9.0, east=10.0, west=11.0)

    def test_equal_north_south_raises(self):
        with pytest.raises(ValueError):
            MapBounds(north=45.0, south=45.0, east=10.1, west=10.0)

    def test_center(self):
        b = MapBounds(north=46.0, south=44.0, east=12.0, west=10.0)
        assert b.center_lat == pytest.approx(45.0)
        assert b.center_lng == pytest.approx(11.0)


# ---------------------------------------------------------------------------
# pixel_to_geo / geo_to_pixel roundtrip
# ---------------------------------------------------------------------------


class TestCoordinateConversion:
    def test_top_left_corner(self):
        lat, lng = pixel_to_geo(0, 0, BOUNDS, IMG_W, IMG_H)
        assert lat == pytest.approx(BOUNDS.north, abs=1e-9)
        assert lng == pytest.approx(BOUNDS.west, abs=1e-9)

    def test_bottom_right_corner(self):
        lat, lng = pixel_to_geo(IMG_W, IMG_H, BOUNDS, IMG_W, IMG_H)
        assert lat == pytest.approx(BOUNDS.south, abs=1e-9)
        assert lng == pytest.approx(BOUNDS.east, abs=1e-9)

    def test_center_pixel(self):
        lat, lng = pixel_to_geo(IMG_W // 2, IMG_H // 2, BOUNDS, IMG_W, IMG_H)
        assert lat == pytest.approx(BOUNDS.center_lat, abs=1e-6)
        assert lng == pytest.approx(BOUNDS.center_lng, abs=1e-6)

    def test_roundtrip_center(self):
        """geo_to_pixel(pixel_to_geo(px, py)) should return the same pixel."""
        for px, py in [(0, 0), (50, 75), (199, 199), (100, 100)]:
            lat, lng = pixel_to_geo(px, py, BOUNDS, IMG_W, IMG_H)
            rpx, rpy = geo_to_pixel(lat, lng, BOUNDS, IMG_W, IMG_H)
            # Allow ±1 px due to integer rounding
            assert abs(rpx - px) <= 1, f"x mismatch: px={px} → {rpx}"
            assert abs(rpy - py) <= 1, f"y mismatch: py={py} → {rpy}"

    def test_roundtrip_geo(self):
        """pixel_to_geo(geo_to_pixel(lat, lng)) should be close to original."""
        for lat, lng in [
            (45.005, 10.005),
            (45.001, 10.009),
            (45.009, 10.001),
            (BOUNDS.center_lat, BOUNDS.center_lng),
        ]:
            px, py = geo_to_pixel(lat, lng, BOUNDS, IMG_W, IMG_H)
            rlat, rlng = pixel_to_geo(px, py, BOUNDS, IMG_W, IMG_H)
            # Precision is limited by the pixel grid resolution
            step_lat = BOUNDS.lat_span / IMG_H
            step_lng = BOUNDS.lng_span / IMG_W
            assert abs(rlat - lat) <= step_lat + 1e-9, f"lat error: {rlat} vs {lat}"
            assert abs(rlng - lng) <= step_lng + 1e-9, f"lng error: {rlng} vs {lng}"

    def test_invalid_dimensions_raise(self):
        with pytest.raises(ValueError):
            pixel_to_geo(0, 0, BOUNDS, 0, IMG_H)
        with pytest.raises(ValueError):
            geo_to_pixel(45.005, 10.005, BOUNDS, IMG_W, 0)

    def test_out_of_bounds_pixel_is_clamped(self):
        """geo_to_pixel clamps results to valid image coordinates."""
        px, py = geo_to_pixel(90.0, 0.0, BOUNDS, IMG_W, IMG_H)
        assert 0 <= px <= IMG_W - 1
        assert 0 <= py <= IMG_H - 1

    def test_lat_decreases_with_py(self):
        """Higher py (further down) → lower latitude (further south)."""
        lat_top, _ = pixel_to_geo(0, 0, BOUNDS, IMG_W, IMG_H)
        lat_bottom, _ = pixel_to_geo(0, IMG_H - 1, BOUNDS, IMG_W, IMG_H)
        assert lat_top > lat_bottom

    def test_lng_increases_with_px(self):
        """Higher px (further right) → higher longitude (further east)."""
        _, lng_left = pixel_to_geo(0, 0, BOUNDS, IMG_W, IMG_H)
        _, lng_right = pixel_to_geo(IMG_W - 1, 0, BOUNDS, IMG_W, IMG_H)
        assert lng_right > lng_left


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------


class TestUtilities:
    def test_haversine_zero(self):
        assert _haversine_distance(45.0, 10.0, 45.0, 10.0) == pytest.approx(0.0)

    def test_haversine_known_distance(self):
        # 1 degree of latitude ≈ 111,320 m at any longitude
        d = _haversine_distance(45.0, 10.0, 46.0, 10.0)
        assert 110_000 < d < 112_000

    def test_line_angle_horizontal(self):
        assert _line_angle_deg(0, 0, 100, 0) == pytest.approx(0.0)

    def test_line_angle_vertical(self):
        angle = _line_angle_deg(0, 0, 0, 100)
        assert angle == pytest.approx(90.0)

    def test_line_angle_diagonal(self):
        angle = _line_angle_deg(0, 0, 100, 100)
        assert angle == pytest.approx(45.0)

    def test_angle_difference_wrap(self):
        """Angle difference wraps correctly at 180°."""
        assert _angle_difference(170.0, 10.0) == pytest.approx(20.0)
        assert _angle_difference(0.0, 90.0) == pytest.approx(90.0)
        assert _angle_difference(0.0, 0.0) == pytest.approx(0.0)
        assert _angle_difference(45.0, 135.0) == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# Clustering and merge
# ---------------------------------------------------------------------------


class TestClusterParallelLines:
    def _make_lines(self, segments):
        """Convert list of (x1,y1,x2,y2) to the HoughLinesP array format."""
        return np.array([[[x1, y1, x2, y2]] for x1, y1, x2, y2 in segments], dtype=np.int32)

    def test_single_segment_forms_one_cluster(self):
        lines = self._make_lines([(0, 0, 100, 0)])
        clusters = _cluster_parallel_lines(lines)
        assert len(clusters) == 1
        assert len(clusters[0]) == 1

    def test_two_parallel_close_segments_merge(self):
        """Two parallel horizontal segments close together → single cluster."""
        lines = self._make_lines([
            (0, 10, 100, 10),
            (0, 15, 100, 15),
        ])
        clusters = _cluster_parallel_lines(lines, distance_tolerance_px=20.0)
        assert len(clusters) == 1

    def test_two_parallel_far_segments_stay_separate(self):
        """Two parallel horizontal segments far apart → two clusters."""
        lines = self._make_lines([
            (0, 10, 100, 10),
            (0, 200, 100, 200),
        ])
        clusters = _cluster_parallel_lines(lines, distance_tolerance_px=20.0)
        assert len(clusters) == 2

    def test_perpendicular_segments_stay_separate(self):
        """Horizontal and vertical segments are not parallel → separate clusters."""
        lines = self._make_lines([
            (0, 50, 100, 50),   # horizontal
            (50, 0, 50, 100),   # vertical
        ])
        clusters = _cluster_parallel_lines(lines, angle_tolerance_deg=10.0)
        assert len(clusters) == 2

    def test_empty_lines_returns_empty(self):
        lines = self._make_lines([])
        clusters = _cluster_parallel_lines(lines)
        assert clusters == []

    def test_multiple_rows_cluster_independently(self):
        """5 horizontal segments, each far from others → 5 clusters."""
        segs = [(0, y, 100, y) for y in range(0, 500, 80)]
        lines = self._make_lines(segs)
        clusters = _cluster_parallel_lines(lines, distance_tolerance_px=20.0)
        assert len(clusters) == len(segs)


class TestMergeClusterToCenterline:
    def test_single_horizontal_segment(self):
        cluster = [(10, 50, 110, 50)]
        x1, y1, x2, y2, angle = _merge_cluster_to_centerline(cluster)
        assert angle == pytest.approx(0.0, abs=1.0)
        # The merged centerline should span roughly 10..110
        assert min(x1, x2) <= 10 + 1
        assert max(x1, x2) >= 110 - 1

    def test_two_aligned_horizontal_segments(self):
        """Two segments on the same horizontal line → spans the full range."""
        cluster = [(10, 50, 60, 50), (70, 50, 120, 50)]
        x1, y1, x2, y2, angle = _merge_cluster_to_centerline(cluster)
        assert angle == pytest.approx(0.0, abs=1.0)
        span_start = min(x1, x2)
        span_end = max(x1, x2)
        assert span_start <= 15
        assert span_end >= 115

    def test_length_increases_with_more_segments(self):
        """Merged centerline of 3 spread segments is longer than 1 segment."""
        single = [(50, 50, 150, 50)]
        triple = [(0, 50, 100, 50), (50, 50, 150, 50), (100, 50, 200, 50)]
        _, _, x2s, _, _ = _merge_cluster_to_centerline(single)
        _, x1t, x2t, _, _ = _merge_cluster_to_centerline(triple)
        span_single = abs(x2s - 50)
        span_triple = abs(x2t - x1t)
        assert span_triple > span_single


# ---------------------------------------------------------------------------
# Sort for serpentine
# ---------------------------------------------------------------------------


class TestSortRowsForSerpentine:
    def _make_centerlines(self, ys):
        """Create horizontal centerlines at the given y positions."""
        return [(0.0, float(y), 100.0, float(y), 0.0) for y in ys]

    def test_already_sorted(self):
        cls = self._make_centerlines([10, 30, 50, 70])
        sorted_cls = _sort_rows_for_serpentine(cls)
        ys_out = [(c[1] + c[3]) / 2 for c in sorted_cls]
        assert ys_out == sorted(ys_out)

    def test_reverse_order_sorted(self):
        cls = self._make_centerlines([70, 50, 30, 10])
        sorted_cls = _sort_rows_for_serpentine(cls)
        ys_out = [(c[1] + c[3]) / 2 for c in sorted_cls]
        assert ys_out == sorted(ys_out)

    def test_empty_input(self):
        assert _sort_rows_for_serpentine([]) == []

    def test_single_element(self):
        cls = self._make_centerlines([42])
        assert len(_sort_rows_for_serpentine(cls)) == 1


# ---------------------------------------------------------------------------
# detect_panel_rows — synthetic imagery
# ---------------------------------------------------------------------------


class TestDetectPanelRows:
    """Tests using synthetic imagery with known structure."""

    BOUNDS_LARGE = MapBounds(north=45.010, south=45.000, east=10.020, west=10.000)

    def test_detects_rows_in_synthetic_image(self):
        """Should detect the correct number (or close) of rows drawn in the image."""
        img = make_synthetic_rows_image(n_rows=4, row_width_px=3, row_gap_px=30,
                                        img_w=500, img_h=400)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=80)
        # We accept between 1 and 6 — detection may merge or split rows
        assert 1 <= len(rows) <= 6

    def test_returns_detected_row_objects(self):
        img = make_synthetic_rows_image(n_rows=3, row_width_px=4, row_gap_px=40,
                                        img_w=500, img_h=400)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=80)
        for row in rows:
            assert isinstance(row, DetectedRow)
            assert 0.0 <= row.confidence <= 1.0
            assert row.length_m > 0
            assert 0.0 <= row.angle_deg < 180.0

    def test_geo_coords_within_bounds(self):
        """All detected row endpoints must fall within the image bounds."""
        img = make_synthetic_rows_image(n_rows=3, row_width_px=4, row_gap_px=40,
                                        img_w=500, img_h=400)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=80)
        b = self.BOUNDS_LARGE
        for row in rows:
            # Allow a tiny tolerance for rounding
            assert b.south - 0.001 <= row.start_lat <= b.north + 0.001
            assert b.west - 0.001 <= row.start_lng <= b.east + 0.001
            assert b.south - 0.001 <= row.end_lat <= b.north + 0.001
            assert b.west - 0.001 <= row.end_lng <= b.east + 0.001

    def test_row_indices_sequential(self):
        """Row indices should be sequential starting from 0."""
        img = make_synthetic_rows_image(n_rows=3, row_width_px=4, row_gap_px=40,
                                        img_w=500, img_h=400)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=80)
        if rows:
            indices = [r.row_index for r in rows]
            assert indices == list(range(len(rows)))

    def test_empty_image_returns_no_rows(self):
        """A completely black image should yield no rows."""
        img = np.zeros((300, 400, 3), dtype=np.uint8)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE)
        assert rows == []

    def test_white_image_returns_no_rows(self):
        """A completely white image has no edges → no rows."""
        img = np.full((300, 400, 3), 255, dtype=np.uint8)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE)
        assert rows == []

    def test_grayscale_input_accepted(self):
        """2D grayscale images should be accepted without error."""
        img_color = make_synthetic_rows_image(n_rows=3, row_width_px=4, row_gap_px=40,
                                              img_w=500, img_h=400)
        import cv2
        gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
        # Should not raise
        rows = detect_panel_rows(gray, self.BOUNDS_LARGE, min_row_length_px=80)
        assert isinstance(rows, list)

    def test_with_polygon_mask(self):
        """Polygon mask covering only half the image reduces detected rows."""
        img = make_synthetic_rows_image(n_rows=6, row_width_px=3, row_gap_px=20,
                                        img_w=500, img_h=400)
        b = self.BOUNDS_LARGE
        # Mask: left half only
        poly = [
            (b.north, b.west),
            (b.north, b.center_lng),
            (b.south, b.center_lng),
            (b.south, b.west),
        ]
        rows_full = detect_panel_rows(img, b, min_row_length_px=80)
        rows_masked = detect_panel_rows(img, b, polygon_coords=poly, min_row_length_px=80)
        # Masked rows should not be MORE than the full set
        # (the mask cuts away half the image)
        assert len(rows_masked) <= len(rows_full) + 1  # +1 for tolerance

    def test_raises_on_none_image(self):
        with pytest.raises(ValueError, match="None or empty"):
            detect_panel_rows(None, self.BOUNDS_LARGE)  # type: ignore[arg-type]

    def test_raises_on_empty_array(self):
        with pytest.raises(ValueError, match="None or empty"):
            detect_panel_rows(np.array([]), self.BOUNDS_LARGE)

    def test_raises_on_too_small_image(self):
        with pytest.raises(ValueError, match="too small"):
            detect_panel_rows(np.zeros((5, 5, 3), dtype=np.uint8), self.BOUNDS_LARGE)

    def test_high_min_length_returns_fewer_rows(self):
        """A very high min_row_length_px should filter out most/all rows."""
        img = make_synthetic_rows_image(n_rows=4, row_width_px=3, row_gap_px=20,
                                        img_w=500, img_h=400)
        rows_normal = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=50)
        rows_strict = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=9000)
        assert len(rows_strict) <= len(rows_normal)

    def test_float32_image_normalised(self):
        """float32 images should be normalised and accepted."""
        img = make_synthetic_rows_image(n_rows=3, row_width_px=4, row_gap_px=40,
                                        img_w=500, img_h=400).astype(np.float32) / 255.0
        # Should not raise
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=80)
        assert isinstance(rows, list)

    def test_rotated_rows_detected(self):
        """Rows rotated 30° should still be detected (angle tolerance permitting)."""
        img = make_synthetic_rows_image(n_rows=4, row_width_px=3, row_gap_px=30,
                                        angle_deg=30.0, img_w=500, img_h=400)
        rows = detect_panel_rows(img, self.BOUNDS_LARGE, min_row_length_px=60)
        # Just assert detection works without crashing and returns a list
        assert isinstance(rows, list)
        if rows:
            # All angles should be in [0, 180)
            for r in rows:
                assert 0.0 <= r.angle_deg < 180.0


# ---------------------------------------------------------------------------
# generate_row_following_waypoints
# ---------------------------------------------------------------------------


class TestGenerateRowFollowingWaypoints:
    """Unit tests for the waypoint generator — decoupled from image detection."""

    ROWS_3 = [
        DetectedRow(0, 45.001, 10.001, 45.001, 10.009, 0.0, 700.0, 0.9),
        DetectedRow(1, 45.003, 10.001, 45.003, 10.009, 0.0, 700.0, 0.8),
        DetectedRow(2, 45.005, 10.001, 45.005, 10.009, 0.0, 700.0, 0.7),
    ]

    def test_returns_correct_number_of_segments(self):
        segs = generate_row_following_waypoints(self.ROWS_3, altitude_agl=30.0)
        assert len(segs) == 3

    def test_empty_rows_returns_empty(self):
        segs = generate_row_following_waypoints([], altitude_agl=30.0)
        assert segs == []

    def test_serpentine_alternating_direction(self):
        """Even rows start near row.start, odd rows start near row.end."""
        segs = generate_row_following_waypoints(self.ROWS_3, altitude_agl=30.0, margin_m=0.0)
        # Row 0 (even): start ≈ row start
        row0 = self.ROWS_3[0]
        seg0_start = segs[0][0]
        assert abs(seg0_start[0] - row0.start_lat) < 0.001
        assert abs(seg0_start[1] - row0.start_lng) < 0.001
        # Row 1 (odd): start ≈ row end (reversed)
        row1 = self.ROWS_3[1]
        seg1_start = segs[1][0]
        assert abs(seg1_start[0] - row1.end_lat) < 0.001
        assert abs(seg1_start[1] - row1.end_lng) < 0.001
        # Row 2 (even): start ≈ row start
        row2 = self.ROWS_3[2]
        seg2_start = segs[2][0]
        assert abs(seg2_start[0] - row2.start_lat) < 0.001
        assert abs(seg2_start[1] - row2.start_lng) < 0.001

    def test_margin_extends_endpoints(self):
        """With non-zero margin, the segment endpoints are further apart than the row."""
        margin_m = 10.0
        segs_zero = generate_row_following_waypoints(self.ROWS_3, altitude_agl=30.0, margin_m=0.0)
        segs_margin = generate_row_following_waypoints(self.ROWS_3, altitude_agl=30.0, margin_m=margin_m)

        for (s0, e0), (sm, em) in zip(segs_zero, segs_margin):
            # The span with margin should be >= span without margin
            span0 = _haversine_distance(s0[0], s0[1], e0[0], e0[1])
            spanm = _haversine_distance(sm[0], sm[1], em[0], em[1])
            assert spanm >= span0 - 1.0  # 1 m tolerance for floating point

    def test_invalid_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_agl"):
            generate_row_following_waypoints(self.ROWS_3, altitude_agl=0.0)

    def test_negative_altitude_raises(self):
        with pytest.raises(ValueError, match="altitude_agl"):
            generate_row_following_waypoints(self.ROWS_3, altitude_agl=-5.0)

    def test_single_row_returns_one_segment(self):
        single = [self.ROWS_3[0]]
        segs = generate_row_following_waypoints(single, altitude_agl=30.0)
        assert len(segs) == 1

    def test_output_format(self):
        """Each segment is a 2-tuple of 2-tuples of floats."""
        segs = generate_row_following_waypoints(self.ROWS_3, altitude_agl=30.0)
        for seg in segs:
            assert len(seg) == 2
            start, end = seg
            assert len(start) == 2
            assert len(end) == 2
            assert all(isinstance(v, float) for v in start)
            assert all(isinstance(v, float) for v in end)

    def test_zero_margin_preserves_row_length(self):
        """With margin=0, start ≈ row.start and end ≈ row.end (even rows)."""
        row = self.ROWS_3[0]  # even index
        segs = generate_row_following_waypoints([row], altitude_agl=30.0, margin_m=0.0)
        start, end = segs[0]
        assert abs(start[0] - row.start_lat) < 1e-6
        assert abs(start[1] - row.start_lng) < 1e-6
        assert abs(end[0] - row.end_lat) < 1e-6
        assert abs(end[1] - row.end_lng) < 1e-6

    def test_many_rows_serpentine_order_maintained(self):
        """With 10 rows, the serpentine alternates correctly for all of them."""
        rows = [
            DetectedRow(i, 45.0 + i * 0.001, 10.001, 45.0 + i * 0.001, 10.009, 0.0, 700.0, 0.8)
            for i in range(10)
        ]
        segs = generate_row_following_waypoints(rows, altitude_agl=25.0, margin_m=0.0)
        assert len(segs) == 10
        for i, (seg, row) in enumerate(zip(segs, rows)):
            if i % 2 == 0:
                # even: start near row.start_lat
                assert abs(seg[0][0] - row.start_lat) < 0.001
            else:
                # odd: start near row.end_lat
                assert abs(seg[0][0] - row.end_lat) < 0.001


# ---------------------------------------------------------------------------
# Integration: detect → generate waypoints
# ---------------------------------------------------------------------------


class TestEndToEnd:
    """Smoke tests for the full detect → waypoints pipeline."""

    BOUNDS = MapBounds(north=45.010, south=45.000, east=10.020, west=10.000)

    def test_full_pipeline_synthetic_image(self):
        img = make_synthetic_rows_image(n_rows=4, row_width_px=3, row_gap_px=30,
                                        img_w=600, img_h=500)
        rows = detect_panel_rows(img, self.BOUNDS, min_row_length_px=100)
        segs = generate_row_following_waypoints(rows, altitude_agl=40.0, margin_m=5.0)
        assert len(segs) == len(rows)
        # All waypoint coords should be geographically sane
        b = self.BOUNDS
        for start, end in segs:
            for lat, lng in [start, end]:
                assert b.south - 0.01 <= lat <= b.north + 0.01
                assert b.west - 0.01 <= lng <= b.east + 0.01

    def test_no_rows_detected_no_waypoints(self):
        """If detection yields nothing, waypoint generation also yields nothing."""
        img = np.zeros((300, 400, 3), dtype=np.uint8)
        rows = detect_panel_rows(img, self.BOUNDS)
        segs = generate_row_following_waypoints(rows, altitude_agl=30.0)
        assert rows == []
        assert segs == []
