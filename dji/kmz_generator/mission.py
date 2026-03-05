"""Data models for DJI WPML waypoint missions.

Models the complete WPML mission structure as used by DJI Pilot 2.
Validated against official DJI WPMZ 1.0.2 specification (Cloud-API-Doc).
"""

from dataclasses import dataclass, field


@dataclass
class WpmlActionParam:
    """Parameters for a WPML action.

    Covers all required fields for: rotateYaw, gimbalRotate, zoom,
    takePhoto, customDirName per the official DJI WPML spec.
    """
    # rotateYaw
    aircraft_heading: float | None = None
    aircraft_path_mode: str = "clockwise"
    # gimbalRotate (ALL fields required per spec)
    payload_position_index: int = 0
    gimbal_heading_yaw_base: str = "north"
    gimbal_rotate_mode: str = "absoluteAngle"
    gimbal_pitch_rotate_enable: int = 1
    gimbal_pitch_rotate_angle: float = -90.0
    gimbal_roll_rotate_enable: int = 0
    gimbal_roll_rotate_angle: float = 0.0
    gimbal_yaw_rotate_enable: int = 0
    gimbal_yaw_rotate_angle: float = 0.0
    gimbal_rotate_time_enable: int = 0
    gimbal_rotate_time: float = 0.0
    # zoom
    focal_length: float | None = None
    # takePhoto (fileSuffix + useGlobalPayloadLensIndex required per spec)
    payload_lens_index: str | None = None
    file_suffix: str = "photo"
    use_global_payload_lens_index: int = 0
    # customDirName
    directory_name: str | None = None


@dataclass
class WpmlAction:
    """A single action within an action group."""
    action_id: int
    action_actuator_func: str  # rotateYaw, gimbalRotate, zoom, takePhoto, customDirName
    params: WpmlActionParam = field(default_factory=WpmlActionParam)


@dataclass
class WpmlActionGroup:
    """An action group triggered at waypoint(s)."""
    action_group_id: int
    action_group_start_index: int
    action_group_end_index: int
    action_group_mode: str = "sequence"
    action_trigger_type: str = "reachPoint"  # reachPoint or multipleTiming
    action_trigger_param: float | None = None  # For multipleTiming: interval in seconds
    actions: list[WpmlAction] = field(default_factory=list)


@dataclass
class WpmlWaypoint:
    """A waypoint in the WPML mission."""
    index: int
    latitude: float
    longitude: float
    execute_height: float       # WGS84 ellipsoid height (absolute altitude)
    relative_height: float      # Height relative to takeoff point (AGL)
    waypoint_speed: float = 3.0
    turn_mode: str = "toPointAndStopWithDiscontinuityCurvature"  # Fixed per DJI spec
    turn_damping_dist: float = 0.0
    use_straight_line: int = 1
    heading_deg: float = 0.0
    heading_path_mode: str = "clockwise"
    row_index: int = 0          # Which flight row this waypoint belongs to


@dataclass
class WpmlMission:
    """Complete WPML mission ready for KMZ export."""
    # Mission metadata
    mission_name: str = "DSI Mapper Mission"
    author: str = "DSI Mapper"

    # Drone configuration
    drone_enum_value: int = 67      # M30T
    drone_sub_enum_value: int = 1
    payload_enum_value: int = 53    # M30T payload
    payload_position_index: int = 0
    payload_lens_index: str = "zoom"

    # Flight parameters
    fly_to_wayline_mode: str = "safely"
    finish_action: str = "goHome"
    exit_on_rc_lost: str = "executeLostAction"
    execute_rc_lost_action: str = "goBack"
    takeoff_security_height: float = 20.0
    global_transitional_speed: float = 3.0
    global_rth_height: float = 100.0
    auto_flight_speed: float = 3.0
    execute_height_mode: str = "WGS84"

    # Heading
    waypoint_heading_mode: str = "manually"
    waypoint_heading_angle: float = 0.0
    waypoint_heading_path_mode: str = "clockwise"
    global_turn_mode: str = "toPointAndStopWithDiscontinuityCurvature"  # Fixed per DJI spec
    global_use_straight_line: int = 1
    global_height: float = 50.0  # Default global height for template.kml

    # Camera/action parameters
    aircraft_yaw: float = 0.0
    gimbal_pitch: float = -90.0
    focal_length: float = 9.1
    timed_photo_interval: float = 1.0

    # Waypoints and actions
    waypoints: list[WpmlWaypoint] = field(default_factory=list)
    action_groups: list[WpmlActionGroup] = field(default_factory=list)

    # Computed mission stats
    total_distance_m: float = 0.0
    total_duration_s: float = 0.0
