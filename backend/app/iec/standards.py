"""IEC 62446-3 constants, thresholds, and classification logic."""

from dataclasses import dataclass
from enum import IntEnum


class IECDefectClass(IntEnum):
    """IEC 62446-3 thermal anomaly severity classes."""
    CLASS_1 = 1  # dT < 10K — monitoring, re-inspect next cycle
    CLASS_2 = 2  # 10K <= dT < 20K — action needed within maintenance window
    CLASS_3 = 3  # dT >= 20K — urgent action, potential safety hazard


# Temperature thresholds (Kelvin delta relative to reference)
IEC_DT_CLASS_2_THRESHOLD = 10.0  # K
IEC_DT_CLASS_3_THRESHOLD = 20.0  # K


def classify_defect(delta_t_kelvin: float) -> IECDefectClass:
    """Classify a thermal anomaly per IEC 62446-3 delta-T thresholds."""
    if delta_t_kelvin >= IEC_DT_CLASS_3_THRESHOLD:
        return IECDefectClass.CLASS_3
    if delta_t_kelvin >= IEC_DT_CLASS_2_THRESHOLD:
        return IECDefectClass.CLASS_2
    return IECDefectClass.CLASS_1


@dataclass(frozen=True)
class IECEnvironmentalLimits:
    """IEC 62446-3 minimum environmental conditions for valid thermographic inspection."""
    min_irradiance_wm2: float = 600.0  # Minimum POA irradiance
    max_wind_speed_ms: float = 6.0  # ~3 Bft (approx)
    min_module_temp_delta_ambient_c: float = 5.0  # Module must be warmer than ambient


IEC_LIMITS = IECEnvironmentalLimits()


def validate_environmental_conditions(
    irradiance_wm2: float,
    wind_speed_ms: float,
    ambient_temp_c: float | None = None,
) -> list[str]:
    """Validate environmental conditions per IEC 62446-3. Returns list of warnings."""
    warnings = []
    if irradiance_wm2 < IEC_LIMITS.min_irradiance_wm2:
        warnings.append(
            f"Irradiance {irradiance_wm2} W/m² below IEC minimum "
            f"({IEC_LIMITS.min_irradiance_wm2} W/m²)"
        )
    if wind_speed_ms > IEC_LIMITS.max_wind_speed_ms:
        warnings.append(
            f"Wind speed {wind_speed_ms} m/s exceeds IEC limit "
            f"({IEC_LIMITS.max_wind_speed_ms} m/s)"
        )
    return warnings
