"""Export WaypointMission to KMZ file for DJI Pilot 2.

DJI Pilot 2 uses KMZ files containing KML with DJI-specific wpml namespace
for waypoint missions. This module generates compliant KMZ files.

Reference: DJI Developer - Waypoint Mission KMZ Format
    https://developer.dji.com/doc/cloud-api-tutorial/en/api-reference/
"""

import io
import zipfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from dji.kmz_generator.mission import WaypointMission

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=False,
    )


def render_kml(mission: WaypointMission) -> str:
    """Render a WaypointMission to DJI-compatible KML string."""
    env = _get_template_env()
    template = env.get_template("waypoint_mission.kml.j2")
    return template.render(mission=mission)


def export_kmz(mission: WaypointMission, output_path: str | Path) -> Path:
    """Export a WaypointMission as a KMZ file for DJI Pilot 2.

    Args:
        mission: The waypoint mission to export.
        output_path: Path for the output .kmz file.

    Returns:
        Path to the created KMZ file.
    """
    output_path = Path(output_path)
    kml_content = render_kml(mission)

    # KMZ is a ZIP file containing wpmz/template.kml and wpmz/waylines.wpml
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("wpmz/template.kml", kml_content)
        # DJI Pilot 2 also expects a waylines.wpml with the same content
        zf.writestr("wpmz/waylines.wpml", kml_content)

    output_path.write_bytes(buf.getvalue())
    return output_path
