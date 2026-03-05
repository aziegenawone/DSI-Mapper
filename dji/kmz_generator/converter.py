"""Convert FlightPlan to WpmlMission with proper DJI action groups.

Ported from DSIdrone generateWaylinesWpml() logic with DJI spec compliance:
- Each waypoint gets a reachPoint action group (rotateYaw + gimbalRotate + zoom)
- Even-index waypoints (row starts) also get customDirName action
- Each row pair (start->end) gets a multipleTiming photo trigger action group
- All action parameters include ALL required fields per DJI WPML spec
"""

from backend.app.services.flight_planner import FlightPlan, CameraPreset
from dji.kmz_generator.mission import (
    WpmlMission,
    WpmlWaypoint,
    WpmlAction,
    WpmlActionParam,
    WpmlActionGroup,
)


def flight_plan_to_wpml_mission(
    plan: FlightPlan,
    mission_name: str = "DSI Mapper Mission",
    terrain_elevations: list[float] | None = None,
) -> WpmlMission:
    """Convert a FlightPlan to a WpmlMission with full action groups.

    Args:
        plan: FlightPlan from flight_planner.build_flight_plan().
        mission_name: Name for the mission.
        terrain_elevations: Optional per-waypoint terrain elevations (WGS84).
            If None, uses altitude_agl as relative height and 0.0 as execute_height.

    Returns:
        WpmlMission ready for KMZ export.
    """
    preset = plan.camera_preset
    focal_length = preset.min_focal_length_mm * plan.zoom_ratio
    focal_length = min(focal_length, preset.max_focal_length_mm)

    # Build WPML waypoints
    wpml_waypoints = []
    for i, wp in enumerate(plan.waypoints):
        terrain_elev = 0.0
        if terrain_elevations and i < len(terrain_elevations):
            terrain_elev = terrain_elevations[i]

        execute_height = terrain_elev + wp.altitude_agl
        wpml_waypoints.append(WpmlWaypoint(
            index=i,
            latitude=wp.latitude,
            longitude=wp.longitude,
            execute_height=execute_height,
            relative_height=wp.altitude_agl,
            waypoint_speed=plan.flight_speed_ms,
            heading_deg=wp.heading_deg,
            row_index=wp.row_index,
        ))

    # Build action groups (ported from DSIdrone, spec-compliant)
    action_groups = []
    action_group_id = 0

    for i, wp in enumerate(wpml_waypoints):
        # --- multipleTiming photo group for each row (start->end) ---
        if i % 2 == 0 and i + 1 < len(wpml_waypoints):
            photo_group = WpmlActionGroup(
                action_group_id=action_group_id,
                action_group_start_index=i,
                action_group_end_index=i + 1,
                action_trigger_type="multipleTiming",
                action_trigger_param=plan.photo_interval_s,
                actions=[
                    WpmlAction(
                        action_id=0,
                        action_actuator_func="takePhoto",
                        params=WpmlActionParam(
                            payload_position_index=preset.payload_position_index,
                            payload_lens_index=preset.payload_lens_index,
                            file_suffix="photo",
                            use_global_payload_lens_index=0,
                        ),
                    ),
                ],
            )
            action_groups.append(photo_group)
            action_group_id += 1

        # --- reachPoint group for each waypoint ---
        reach_actions = [
            # Action 0: rotateYaw
            WpmlAction(
                action_id=0,
                action_actuator_func="rotateYaw",
                params=WpmlActionParam(
                    aircraft_heading=plan.waypoints[i].heading_deg,
                    aircraft_path_mode="clockwise",
                ),
            ),
            # Action 1: gimbalRotate (ALL 10+ required fields per DJI spec)
            WpmlAction(
                action_id=1,
                action_actuator_func="gimbalRotate",
                params=WpmlActionParam(
                    payload_position_index=preset.payload_position_index,
                    gimbal_heading_yaw_base="north",
                    gimbal_rotate_mode="absoluteAngle",
                    gimbal_pitch_rotate_enable=1,
                    gimbal_pitch_rotate_angle=plan.gimbal_pitch_deg,
                    gimbal_roll_rotate_enable=0,
                    gimbal_roll_rotate_angle=0.0,
                    gimbal_yaw_rotate_enable=0,
                    gimbal_yaw_rotate_angle=0.0,
                    gimbal_rotate_time_enable=0,
                    gimbal_rotate_time=0.0,
                ),
            ),
            # Action 2: zoom
            WpmlAction(
                action_id=2,
                action_actuator_func="zoom",
                params=WpmlActionParam(
                    payload_position_index=preset.payload_position_index,
                    focal_length=focal_length,
                ),
            ),
        ]

        # Action 3: customDirName only for row starts (even-index waypoints)
        if i % 2 == 0:
            row_number = (i // 2) + 1
            reach_actions.append(
                WpmlAction(
                    action_id=3,
                    action_actuator_func="customDirName",
                    params=WpmlActionParam(
                        payload_position_index=preset.payload_position_index,
                        directory_name=f"ROW {row_number}",
                    ),
                )
            )

        reach_group = WpmlActionGroup(
            action_group_id=action_group_id,
            action_group_start_index=i,
            action_group_end_index=i,
            action_trigger_type="reachPoint",
            actions=reach_actions,
        )
        action_groups.append(reach_group)
        action_group_id += 1

    mission = WpmlMission(
        mission_name=mission_name,
        drone_enum_value=preset.drone_enum_value,
        drone_sub_enum_value=preset.drone_sub_enum_value,
        payload_enum_value=preset.payload_enum_value,
        payload_position_index=preset.payload_position_index,
        payload_lens_index=preset.payload_lens_index,
        auto_flight_speed=plan.flight_speed_ms,
        global_transitional_speed=plan.flight_speed_ms,
        waypoint_heading_angle=plan.waypoints[0].heading_deg if plan.waypoints else 0.0,
        aircraft_yaw=plan.waypoints[0].heading_deg if plan.waypoints else 0.0,
        gimbal_pitch=plan.gimbal_pitch_deg,
        focal_length=focal_length,
        timed_photo_interval=plan.photo_interval_s,
        global_height=plan.altitude_agl,
        waypoints=wpml_waypoints,
        action_groups=action_groups,
        total_distance_m=plan.estimated_distance_m,
        total_duration_s=plan.estimated_duration_s,
    )

    return mission
