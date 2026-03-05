"""Python wrapper for DJI Thermal SDK (TSDK / libdirp).

The DJI Thermal SDK provides functions to decode R-JPEG thermal images
from DJI cameras (Zenmuse H20T, Mavic 3T, M30T, etc.) and extract
per-pixel temperature data.

Prerequisites:
    1. Download DJI Thermal SDK from https://www.dji.com/downloads/softwares/dji-thermal-sdk
    2. Place libdirp.dll (Windows) or libdirp.so (Linux) in this directory
    3. Also place libv_dirp.dll / libv_dirp.so alongside it

Usage:
    from dji.thermal_sdk import decode_rjpeg

    temperature_matrix = decode_rjpeg(
        "path/to/image.jpg",
        emissivity=0.95,
        distance=25.0,
        humidity=70.0,
        reflection_temp=25.0,
    )
    # temperature_matrix is a numpy float32 array (H x W) in degrees Celsius
"""

from dji.thermal_sdk.rjpeg_decoder import decode_rjpeg, ThermalParams

__all__ = ["decode_rjpeg", "ThermalParams"]
