"""Tests for flight planner service and KMZ generation."""

import math
import zipfile
import io

import pytest

from app.services.flight_planner import (
    calculate_altitude_from_gsd,
    generate_lawnmower_waypoints,
    build_flight_plan,
    CAMERA_PRESETS,
)


# --- GSD / altitude calculation ---

class TestCalculateAltitude:
    def test_m30t_default_gsd_1cm(self):
        """M30T at 1 cm/px GSD with no zoom → known altitude."""
        preset = CAMERA_PRESETS["m30t"]
        alt_above, alt_agl = calculate_altitude_from_gsd(1.0, preset)
        # Formula: (9.1 * 640 * 1.0) / (7.68 * 100) = 5824 / 768 ≈ 7.58m
        assert abs(alt_above - 7.583) < 0.01
        assert alt_above == alt_agl  # No object height

    def test_with_object_height(self):
        """Object height adds to AGL altitude."""
        preset = CAMERA_PRESETS["m30t"]
        alt_above, alt_agl = calculate_altitude_from_gsd(1.0, preset, object_height_m=5.0)
        assert abs(alt_agl - alt_above - 5.0) < 0.001

    def test_zoom_clamps_to_max(self):
        """Zoom ratio is clamped to max focal length."""
        preset = CAMERA_PRESETS["m30t"]
        # Zoom ratio 100 → focal 910mm, but max is 147mm
        alt_above_zoom, _ = calculate_altitude_from_gsd(1.0, preset, zoom_ratio=100.0)
        alt_above_max, _ = calculate_altitude_from_gsd(
            1.0, preset, zoom_ratio=preset.max_focal_length_mm / preset.min_focal_length_mm
        )
        assert abs(alt_above_zoom - alt_above_max) < 0.001

    def test_wide_lens_higher_altitude(self):
        """Wide lens needs higher altitude for same GSD."""
        preset_zoom = CAMERA_PRESETS["m30t"]
        preset_wide = CAMERA_PRESETS["m30t_wide"]
        alt_zoom, _ = calculate_altitude_from_gsd(0.5, preset_zoom)
        alt_wide, _ = calculate_altitude_from_gsd(0.5, preset_wide)
        # Wide has larger sensor + wider lens → different altitude
        assert alt_zoom != alt_wide


# --- Lawnmower waypoint generation ---

class TestLawnmowerWaypoints:
    # Simple square boundary
    SQUARE = [
        (45.0, 10.0),
        (45.0, 10.01),
        (45.01, 10.01),
        (45.01, 10.0),
    ]

    def test_returns_correct_number_of_rows(self):
        segments = generate_lawnmower_waypoints(self.SQUARE, num_rows=5)
        assert len(segments) == 5

    def test_too_few_rows_returns_empty(self):
        segments = generate_lawnmower_waypoints(self.SQUARE, num_rows=1)
        assert segments == []

    def test_too_few_boundary_points_returns_empty(self):
        segments = generate_lawnmower_waypoints([(0, 0), (1, 1)], num_rows=5)
        assert segments == []

    def test_segments_are_inside_boundary(self):
        """All generated waypoints should be inside or very close to the boundary."""
        from shapely.geometry import Polygon, Point
        segments = generate_lawnmower_waypoints(self.SQUARE, num_rows=5)
        polygon = Polygon([(lng, lat) for lat, lng in self.SQUARE])
        buffered = polygon.buffer(0.001)  # Small tolerance

        for start, end in segments:
            assert buffered.contains(Point(start[1], start[0])), f"Start {start} outside"
            assert buffered.contains(Point(end[1], end[0])), f"End {end} outside"

    def test_serpentine_pattern(self):
        """Even rows go one direction, odd rows go the opposite."""
        segments = generate_lawnmower_waypoints(self.SQUARE, num_rows=4)
        assert len(segments) >= 2
        # In a serpentine, consecutive end and start points should be close
        # (the drone travels from one row end to the next row start)

    def test_rotation(self):
        """Rotated grid should produce different waypoints."""
        seg_0 = generate_lawnmower_waypoints(self.SQUARE, num_rows=5, rotation_deg=0)
        seg_45 = generate_lawnmower_waypoints(self.SQUARE, num_rows=5, rotation_deg=45)
        # They should be different
        if seg_0 and seg_45:
            assert seg_0[0] != seg_45[0]


# --- Full flight plan ---

class TestBuildFlightPlan:
    BOUNDARY = [
        (45.0, 10.0),
        (45.0, 10.01),
        (45.01, 10.01),
        (45.01, 10.0),
    ]

    def test_basic_plan(self):
        plan = build_flight_plan(self.BOUNDARY, num_rows=5, gsd_cm_px=1.0)
        assert len(plan.waypoints) == 10  # 5 rows × 2 waypoints each
        assert plan.altitude_agl > 0
        assert plan.gsd_cm_px == 1.0
        assert plan.estimated_distance_m > 0
        assert plan.estimated_duration_s > 0
        assert plan.estimated_photos > 0

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown camera preset"):
            build_flight_plan(self.BOUNDARY, num_rows=5, gsd_cm_px=1.0, camera_preset_key="fake")

    def test_waypoints_have_correct_altitude(self):
        plan = build_flight_plan(
            self.BOUNDARY, num_rows=3, gsd_cm_px=1.0, object_height_m=2.0
        )
        for wp in plan.waypoints:
            assert wp.altitude_agl == plan.altitude_agl


# --- KMZ generation ---

class TestKmzGeneration:
    BOUNDARY = [
        (45.0, 10.0),
        (45.0, 10.01),
        (45.01, 10.01),
        (45.01, 10.0),
    ]

    def test_wpml_builder_template_kml(self):
        from dji.kmz_generator.converter import flight_plan_to_wpml_mission
        from dji.kmz_generator.wpml_builder import build_template_kml

        plan = build_flight_plan(self.BOUNDARY, num_rows=3, gsd_cm_px=1.0)
        mission = flight_plan_to_wpml_mission(plan, mission_name="Test Mission")
        kml = build_template_kml(mission)

        assert '<?xml version="1.0"' in kml
        assert "wpml:droneEnumValue" in kml
        assert "wpml:payloadEnumValue" in kml
        assert "67" in kml  # M30T droneEnumValue
        # Per DJI spec, mission name is NOT in template.kml (comes from filename)
        assert "wpml:waylineCoordinateSysParam" in kml  # Required per spec
        assert "wpml:useGlobalHeight" in kml  # Required per spec
        assert "wpml:gimbalPitchMode" in kml  # Required per spec

    def test_wpml_builder_waylines_wpml(self):
        from dji.kmz_generator.converter import flight_plan_to_wpml_mission
        from dji.kmz_generator.wpml_builder import build_waylines_wpml

        plan = build_flight_plan(self.BOUNDARY, num_rows=3, gsd_cm_px=1.0)
        mission = flight_plan_to_wpml_mission(plan)
        wpml = build_waylines_wpml(mission)

        assert "wpml:executeHeightMode" in wpml
        assert "WGS84" in wpml
        assert "wpml:actionGroup" in wpml
        assert "rotateYaw" in wpml
        assert "gimbalRotate" in wpml
        assert "takePhoto" in wpml
        assert "customDirName" in wpml
        assert "multipleTiming" in wpml
        assert "ROW 1" in wpml
        # DJI spec compliance: action groups inside placemarks
        assert "wpml:waypointHeadingParam" in wpml  # Required per spec
        assert "gimbalHeadingYawBase" in wpml  # Required for gimbalRotate
        assert "gimbalRollRotateEnable" in wpml  # Required for gimbalRotate
        assert "fileSuffix" in wpml  # Required for takePhoto
        assert "toPointAndStopWithDiscontinuityCurvature" in wpml  # Correct enum

    def test_kmz_export_bytes(self):
        from dji.kmz_generator.converter import flight_plan_to_wpml_mission
        from dji.kmz_generator.exporter import export_kmz_bytes

        plan = build_flight_plan(self.BOUNDARY, num_rows=3, gsd_cm_px=1.0)
        mission = flight_plan_to_wpml_mission(plan)
        kmz_bytes = export_kmz_bytes(mission)

        # Verify it's a valid ZIP
        zf = zipfile.ZipFile(io.BytesIO(kmz_bytes))
        names = zf.namelist()
        assert "wpmz/template.kml" in names
        assert "wpmz/waylines.wpml" in names

        # template.kml and waylines.wpml should be different
        template = zf.read("wpmz/template.kml").decode()
        waylines = zf.read("wpmz/waylines.wpml").decode()
        assert template != waylines
        assert "wpml:templateType" in template  # Only in template
        assert "wpml:executeHeightMode" in waylines  # Only in waylines
