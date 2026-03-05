"""Python ctypes wrapper for DJI Thermal SDK (libdirp).

This module provides a Python interface to decode DJI R-JPEG thermal images
and extract per-pixel temperature matrices.

Reference: DJI Thermal SDK Documentation
    - dirp_create_from_rjpeg: Create handle from R-JPEG file
    - dirp_set_measurement_params: Set emissivity, distance, etc.
    - dirp_measure_ex: Extract temperature array (float32, degrees C)
    - dirp_destroy: Clean up handle
"""

import ctypes
import os
import platform
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Determine library name based on platform
_LIB_DIR = Path(__file__).parent
if platform.system() == "Windows":
    _LIB_NAME = "libdirp.dll"
else:
    _LIB_NAME = "libdirp.so"

_LIB_PATH = _LIB_DIR / _LIB_NAME


@dataclass
class ThermalParams:
    """Measurement parameters for thermal image processing."""
    emissivity: float = 0.95  # PV glass ~0.95
    distance: float = 25.0    # meters (flight altitude)
    humidity: float = 70.0    # percent
    reflection_temp: float = 25.0  # degrees Celsius (reflected apparent temperature)


# C struct equivalents for DJI Thermal SDK
class _DirpMeasurementParams(ctypes.Structure):
    _fields_ = [
        ("distance", ctypes.c_float),
        ("humidity", ctypes.c_float),
        ("emissivity", ctypes.c_float),
        ("reflection", ctypes.c_float),
    ]


class _DirpResolution(ctypes.Structure):
    _fields_ = [
        ("width", ctypes.c_int32),
        ("height", ctypes.c_int32),
    ]


def _load_sdk():
    """Load DJI Thermal SDK shared library."""
    if not _LIB_PATH.exists():
        raise FileNotFoundError(
            f"DJI Thermal SDK not found at {_LIB_PATH}. "
            f"Download from https://www.dji.com/downloads/softwares/dji-thermal-sdk "
            f"and place {_LIB_NAME} in {_LIB_DIR}"
        )
    return ctypes.CDLL(str(_LIB_PATH))


def decode_rjpeg(
    image_path: str | Path,
    params: ThermalParams | None = None,
) -> np.ndarray:
    """Decode a DJI R-JPEG thermal image to a temperature matrix.

    Args:
        image_path: Path to R-JPEG file from DJI thermal camera.
        params: Measurement parameters (emissivity, distance, humidity, reflection temp).

    Returns:
        numpy float32 array of shape (H, W) with temperature values in degrees Celsius.

    Raises:
        FileNotFoundError: If SDK library or image file not found.
        RuntimeError: If SDK function call fails.
    """
    if params is None:
        params = ThermalParams()

    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    # Read image file into memory
    image_data = image_path.read_bytes()
    image_buf = ctypes.create_string_buffer(image_data)

    lib = _load_sdk()

    # Create handle from R-JPEG
    handle = ctypes.c_void_p()
    ret = lib.dirp_create_from_rjpeg(
        image_buf,
        ctypes.c_int32(len(image_data)),
        ctypes.byref(handle),
    )
    if ret != 0:
        raise RuntimeError(f"dirp_create_from_rjpeg failed with code {ret}")

    try:
        # Get image resolution
        resolution = _DirpResolution()
        ret = lib.dirp_get_rjpeg_resolution(handle, ctypes.byref(resolution))
        if ret != 0:
            raise RuntimeError(f"dirp_get_rjpeg_resolution failed with code {ret}")

        width, height = resolution.width, resolution.height

        # Set measurement parameters
        m_params = _DirpMeasurementParams(
            distance=params.distance,
            humidity=params.humidity,
            emissivity=params.emissivity,
            reflection=params.reflection_temp,
        )
        ret = lib.dirp_set_measurement_params(handle, ctypes.byref(m_params))
        if ret != 0:
            raise RuntimeError(f"dirp_set_measurement_params failed with code {ret}")

        # Extract temperature array
        size = width * height
        temp_buf = (ctypes.c_float * size)()
        ret = lib.dirp_measure_ex(handle, temp_buf, ctypes.c_int32(size))
        if ret != 0:
            raise RuntimeError(f"dirp_measure_ex failed with code {ret}")

        # Convert to numpy array
        temp_array = np.ctypeslib.as_array(temp_buf).reshape((height, width)).copy()
        return temp_array

    finally:
        lib.dirp_destroy(handle)
