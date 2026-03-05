"""Build DJI WPML XML content for template.kml and waylines.wpml.

Validated against official DJI WPMZ 1.0.2 specification:
- https://github.com/dji-sdk/Cloud-API-Doc/blob/master/docs/en/60.api-reference/00.dji-wpml/

Key fixes vs initial version:
- Action groups INSIDE placemarks (not after them)
- All required gimbalRotate params (10 fields)
- takePhoto includes fileSuffix + useGlobalPayloadLensIndex
- waypointHeadingParam in waylines.wpml placemarks
- waylineCoordinateSysParam in template.kml
- useGlobal* flags in template.kml placemarks
- Correct turn mode enum: toPointAndStopWithDiscontinuityCurvature
- Namespace version 1.0.2 for compatibility
"""

import time
from xml.sax.saxutils import escape

from dji.kmz_generator.mission import WpmlMission, WpmlWaypoint, WpmlActionGroup

# WPML namespace version — 1.0.2 matches official DJI spec samples
WPML_NS = "http://www.dji.com/wpmz/1.0.2"


def _build_action_xml(action, indent: str = "          ") -> str:
    """Build XML for a single action with all required params per DJI spec."""
    lines = [
        f"{indent}<wpml:action>",
        f"{indent}  <wpml:actionId>{action.action_id}</wpml:actionId>",
        f"{indent}  <wpml:actionActuatorFunc>{action.action_actuator_func}</wpml:actionActuatorFunc>",
        f"{indent}  <wpml:actionActuatorFuncParam>",
    ]

    p = action.params
    func = action.action_actuator_func
    pi = f"{indent}    "  # param indent

    if func == "rotateYaw":
        lines.append(f"{pi}<wpml:aircraftHeading>{p.aircraft_heading}</wpml:aircraftHeading>")
        lines.append(f"{pi}<wpml:aircraftPathMode>{p.aircraft_path_mode}</wpml:aircraftPathMode>")

    elif func == "gimbalRotate":
        # ALL 10+ fields required per official DJI WPML spec
        lines.append(f"{pi}<wpml:gimbalHeadingYawBase>{p.gimbal_heading_yaw_base}</wpml:gimbalHeadingYawBase>")
        lines.append(f"{pi}<wpml:gimbalRotateMode>{p.gimbal_rotate_mode}</wpml:gimbalRotateMode>")
        lines.append(f"{pi}<wpml:gimbalPitchRotateEnable>{p.gimbal_pitch_rotate_enable}</wpml:gimbalPitchRotateEnable>")
        lines.append(f"{pi}<wpml:gimbalPitchRotateAngle>{p.gimbal_pitch_rotate_angle}</wpml:gimbalPitchRotateAngle>")
        lines.append(f"{pi}<wpml:gimbalRollRotateEnable>{p.gimbal_roll_rotate_enable}</wpml:gimbalRollRotateEnable>")
        lines.append(f"{pi}<wpml:gimbalRollRotateAngle>{p.gimbal_roll_rotate_angle}</wpml:gimbalRollRotateAngle>")
        lines.append(f"{pi}<wpml:gimbalYawRotateEnable>{p.gimbal_yaw_rotate_enable}</wpml:gimbalYawRotateEnable>")
        lines.append(f"{pi}<wpml:gimbalYawRotateAngle>{p.gimbal_yaw_rotate_angle}</wpml:gimbalYawRotateAngle>")
        lines.append(f"{pi}<wpml:gimbalRotateTimeEnable>{p.gimbal_rotate_time_enable}</wpml:gimbalRotateTimeEnable>")
        lines.append(f"{pi}<wpml:gimbalRotateTime>{p.gimbal_rotate_time}</wpml:gimbalRotateTime>")
        lines.append(f"{pi}<wpml:payloadPositionIndex>{p.payload_position_index}</wpml:payloadPositionIndex>")

    elif func == "zoom":
        lines.append(f"{pi}<wpml:payloadPositionIndex>{p.payload_position_index}</wpml:payloadPositionIndex>")
        lines.append(f"{pi}<wpml:focalLength>{p.focal_length:.1f}</wpml:focalLength>")

    elif func == "takePhoto":
        # fileSuffix + useGlobalPayloadLensIndex required per spec
        lines.append(f"{pi}<wpml:payloadPositionIndex>{p.payload_position_index}</wpml:payloadPositionIndex>")
        lines.append(f"{pi}<wpml:payloadLensIndex>{p.payload_lens_index}</wpml:payloadLensIndex>")
        lines.append(f"{pi}<wpml:useGlobalPayloadLensIndex>{p.use_global_payload_lens_index}</wpml:useGlobalPayloadLensIndex>")
        lines.append(f"{pi}<wpml:fileSuffix>{p.file_suffix}</wpml:fileSuffix>")

    elif func == "customDirName":
        lines.append(f"{pi}<wpml:payloadPositionIndex>{p.payload_position_index}</wpml:payloadPositionIndex>")
        lines.append(f"{pi}<wpml:directoryName>{escape(p.directory_name)}</wpml:directoryName>")

    lines.append(f"{indent}  </wpml:actionActuatorFuncParam>")
    lines.append(f"{indent}</wpml:action>")
    return "\n".join(lines)


def _build_action_group_xml(group: WpmlActionGroup, indent: str = "      ") -> str:
    """Build XML for an action group."""
    lines = [
        f"{indent}<wpml:actionGroup>",
        f"{indent}  <wpml:actionGroupId>{group.action_group_id}</wpml:actionGroupId>",
        f"{indent}  <wpml:actionGroupStartIndex>{group.action_group_start_index}</wpml:actionGroupStartIndex>",
        f"{indent}  <wpml:actionGroupEndIndex>{group.action_group_end_index}</wpml:actionGroupEndIndex>",
        f"{indent}  <wpml:actionGroupMode>{group.action_group_mode}</wpml:actionGroupMode>",
        f"{indent}  <wpml:actionTrigger>",
        f"{indent}    <wpml:actionTriggerType>{group.action_trigger_type}</wpml:actionTriggerType>",
    ]

    if group.action_trigger_type == "multipleTiming" and group.action_trigger_param is not None:
        lines.append(f"{indent}    <wpml:actionTriggerParam>{group.action_trigger_param}</wpml:actionTriggerParam>")

    lines.append(f"{indent}  </wpml:actionTrigger>")

    for action in group.actions:
        lines.append(_build_action_xml(action, indent=f"{indent}  "))

    lines.append(f"{indent}</wpml:actionGroup>")
    return "\n".join(lines)


def _build_mission_config_xml(mission: WpmlMission, include_rth: bool = False) -> str:
    """Build missionConfig XML block shared between template.kml and waylines.wpml."""
    lines = [
        "    <wpml:missionConfig>",
        f"      <wpml:flyToWaylineMode>{mission.fly_to_wayline_mode}</wpml:flyToWaylineMode>",
        f"      <wpml:finishAction>{mission.finish_action}</wpml:finishAction>",
        f"      <wpml:exitOnRCLost>{mission.exit_on_rc_lost}</wpml:exitOnRCLost>",
        f"      <wpml:executeRCLostAction>{mission.execute_rc_lost_action}</wpml:executeRCLostAction>",
        f"      <wpml:takeOffSecurityHeight>{mission.takeoff_security_height}</wpml:takeOffSecurityHeight>",
        f"      <wpml:globalTransitionalSpeed>{mission.global_transitional_speed}</wpml:globalTransitionalSpeed>",
    ]
    if include_rth:
        lines.append(f"      <wpml:globalRTHHeight>{mission.global_rth_height}</wpml:globalRTHHeight>")
    lines.extend([
        "      <wpml:droneInfo>",
        f"        <wpml:droneEnumValue>{mission.drone_enum_value}</wpml:droneEnumValue>",
        f"        <wpml:droneSubEnumValue>{mission.drone_sub_enum_value}</wpml:droneSubEnumValue>",
        "      </wpml:droneInfo>",
        "      <wpml:payloadInfo>",
        f"        <wpml:payloadEnumValue>{mission.payload_enum_value}</wpml:payloadEnumValue>",
        f"        <wpml:payloadPositionIndex>{mission.payload_position_index}</wpml:payloadPositionIndex>",
        "      </wpml:payloadInfo>",
        "    </wpml:missionConfig>",
    ])
    return "\n".join(lines)


def build_template_kml(mission: WpmlMission) -> str:
    """Build template.kml — simplified waypoint list for DJI Pilot 2 preview.

    Validated against official DJI spec: includes waylineCoordinateSysParam,
    gimbalPitchMode, useGlobal* flags, and globalHeight.
    """
    now = int(time.time() * 1000)

    # Build placemarks with useGlobal* flags
    placemarks = []
    for wp in mission.waypoints:
        placemarks.append(
            f"      <Placemark>\n"
            f"        <Point><coordinates>{wp.longitude:.9f},{wp.latitude:.9f}</coordinates></Point>\n"
            f"        <wpml:index>{wp.index}</wpml:index>\n"
            f"        <wpml:ellipsoidHeight>{wp.execute_height:.2f}</wpml:ellipsoidHeight>\n"
            f"        <wpml:height>{wp.relative_height:.2f}</wpml:height>\n"
            f"        <wpml:useGlobalHeight>1</wpml:useGlobalHeight>\n"
            f"        <wpml:useGlobalSpeed>1</wpml:useGlobalSpeed>\n"
            f"        <wpml:useGlobalHeadingParam>1</wpml:useGlobalHeadingParam>\n"
            f"        <wpml:useGlobalTurnParam>1</wpml:useGlobalTurnParam>\n"
            f"        <wpml:gimbalPitchAngle>{mission.gimbal_pitch}</wpml:gimbalPitchAngle>\n"
            f"      </Placemark>"
        )

    mission_config = _build_mission_config_xml(mission, include_rth=False)

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="{WPML_NS}">\n'
        f'  <Document>\n'
        f'    <wpml:author>{escape(mission.author)}</wpml:author>\n'
        f'    <wpml:createTime>{now}</wpml:createTime>\n'
        f'    <wpml:updateTime>{now}</wpml:updateTime>\n'
        f'{mission_config}\n'
        f'    <Folder>\n'
        f'      <wpml:templateType>waypoint</wpml:templateType>\n'
        f'      <wpml:templateId>0</wpml:templateId>\n'
        f'      <wpml:waylineCoordinateSysParam>\n'
        f'        <wpml:coordinateMode>WGS84</wpml:coordinateMode>\n'
        f'        <wpml:heightMode>EGM96</wpml:heightMode>\n'
        f'        <wpml:positioningType>GPS</wpml:positioningType>\n'
        f'      </wpml:waylineCoordinateSysParam>\n'
        f'      <wpml:autoFlightSpeed>{mission.auto_flight_speed}</wpml:autoFlightSpeed>\n'
        f'      <wpml:globalHeight>{mission.global_height}</wpml:globalHeight>\n'
        f'      <wpml:gimbalPitchMode>usePointSetting</wpml:gimbalPitchMode>\n'
        f'      <wpml:globalWaypointHeadingParam>\n'
        f'        <wpml:waypointHeadingMode>{mission.waypoint_heading_mode}</wpml:waypointHeadingMode>\n'
        f'        <wpml:waypointHeadingAngle>{mission.waypoint_heading_angle}</wpml:waypointHeadingAngle>\n'
        f'        <wpml:waypointHeadingPathMode>{mission.waypoint_heading_path_mode}</wpml:waypointHeadingPathMode>\n'
        f'      </wpml:globalWaypointHeadingParam>\n'
        f'      <wpml:globalWaypointTurnMode>{mission.global_turn_mode}</wpml:globalWaypointTurnMode>\n'
        f'      <wpml:globalUseStraightLine>{mission.global_use_straight_line}</wpml:globalUseStraightLine>\n'
        + "\n".join(placemarks) + "\n"
        f'    </Folder>\n'
        f'  </Document>\n'
        f'</kml>'
    )


def build_waylines_wpml(mission: WpmlMission) -> str:
    """Build waylines.wpml — full execution data with action groups INSIDE placemarks.

    Key structural requirement: action groups must be nested inside the Placemark
    of their start waypoint, not placed as siblings after all placemarks.
    """
    # Index action groups by their start waypoint for embedding inside placemarks
    groups_by_start = {}
    for group in mission.action_groups:
        start_idx = group.action_group_start_index
        if start_idx not in groups_by_start:
            groups_by_start[start_idx] = []
        groups_by_start[start_idx].append(group)

    # Build waypoint placemarks with embedded action groups
    placemarks = []
    for wp in mission.waypoints:
        lines = [
            f"    <Placemark>",
            f"      <Point><coordinates>{wp.longitude:.9f},{wp.latitude:.9f}</coordinates></Point>",
            f"      <wpml:index>{wp.index}</wpml:index>",
            f"      <wpml:executeHeight>{wp.execute_height:.3f}</wpml:executeHeight>",
            f"      <wpml:waypointSpeed>{wp.waypoint_speed}</wpml:waypointSpeed>",
            f"      <wpml:waypointHeadingParam>",
            f"        <wpml:waypointHeadingMode>manually</wpml:waypointHeadingMode>",
            f"        <wpml:waypointHeadingAngle>{wp.heading_deg}</wpml:waypointHeadingAngle>",
            f"        <wpml:waypointHeadingPathMode>{wp.heading_path_mode}</wpml:waypointHeadingPathMode>",
            f"      </wpml:waypointHeadingParam>",
            f"      <wpml:waypointTurnParam>",
            f"        <wpml:waypointTurnMode>{wp.turn_mode}</wpml:waypointTurnMode>",
            f"        <wpml:waypointTurnDampingDist>{wp.turn_damping_dist}</wpml:waypointTurnDampingDist>",
            f"      </wpml:waypointTurnParam>",
            f"      <wpml:useStraightLine>{wp.use_straight_line}</wpml:useStraightLine>",
        ]

        # Embed action groups that start at this waypoint
        if wp.index in groups_by_start:
            for group in groups_by_start[wp.index]:
                lines.append(_build_action_group_xml(group, indent="      "))

        lines.append(f"    </Placemark>")
        placemarks.append("\n".join(lines))

    mission_config = _build_mission_config_xml(mission, include_rth=True)

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:wpml="{WPML_NS}">\n'
        f'  <Document>\n'
        f'{mission_config}\n'
        f'    <Folder>\n'
        f'      <wpml:templateId>0</wpml:templateId>\n'
        f'      <wpml:executeHeightMode>{mission.execute_height_mode}</wpml:executeHeightMode>\n'
        f'      <wpml:waylineId>0</wpml:waylineId>\n'
        f'      <wpml:autoFlightSpeed>{mission.auto_flight_speed}</wpml:autoFlightSpeed>\n'
        + "\n".join(placemarks) + "\n"
        f'    </Folder>\n'
        f'  </Document>\n'
        f'</kml>'
    )
