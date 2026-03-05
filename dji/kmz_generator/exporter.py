"""Export WPML missions to KMZ file for DJI Pilot 2.

DJI Pilot 2 KMZ files contain two separate XML files inside wpmz/:
- template.kml: Simplified preview with waypoint coordinates
- waylines.wpml: Full execution data with action groups and WGS84 heights

Reference: DJI WPMZ 1.0.6 specification
"""

import io
import zipfile
from pathlib import Path

from dji.kmz_generator.mission import WpmlMission
from dji.kmz_generator.wpml_builder import build_template_kml, build_waylines_wpml


def export_kmz(mission: WpmlMission, output_path: str | Path) -> Path:
    """Export a WpmlMission as a KMZ file for DJI Pilot 2.

    The KMZ is a ZIP containing:
    - wpmz/template.kml (preview/template data)
    - wpmz/waylines.wpml (full execution data with action groups)

    Args:
        mission: The WPML mission to export.
        output_path: Path for the output .kmz file.

    Returns:
        Path to the created KMZ file.
    """
    output_path = Path(output_path)

    template_kml = build_template_kml(mission)
    waylines_wpml = build_waylines_wpml(mission)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("wpmz/template.kml", template_kml)
        zf.writestr("wpmz/waylines.wpml", waylines_wpml)

    output_path.write_bytes(buf.getvalue())
    return output_path


def export_kmz_bytes(mission: WpmlMission) -> bytes:
    """Export a WpmlMission as KMZ bytes (for HTTP streaming response).

    Returns:
        KMZ file content as bytes.
    """
    template_kml = build_template_kml(mission)
    waylines_wpml = build_waylines_wpml(mission)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("wpmz/template.kml", template_kml)
        zf.writestr("wpmz/waylines.wpml", waylines_wpml)

    return buf.getvalue()
