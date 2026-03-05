"""Tests for IEC 62446-3 classification and validation logic."""

from app.iec.standards import (
    IECDefectClass,
    classify_defect,
    validate_environmental_conditions,
)


def test_classify_class_1():
    assert classify_defect(5.0) == IECDefectClass.CLASS_1
    assert classify_defect(9.9) == IECDefectClass.CLASS_1


def test_classify_class_2():
    assert classify_defect(10.0) == IECDefectClass.CLASS_2
    assert classify_defect(15.0) == IECDefectClass.CLASS_2
    assert classify_defect(19.9) == IECDefectClass.CLASS_2


def test_classify_class_3():
    assert classify_defect(20.0) == IECDefectClass.CLASS_3
    assert classify_defect(50.0) == IECDefectClass.CLASS_3


def test_env_conditions_valid():
    warnings = validate_environmental_conditions(
        irradiance_wm2=800.0, wind_speed_ms=3.0
    )
    assert warnings == []


def test_env_conditions_low_irradiance():
    warnings = validate_environmental_conditions(
        irradiance_wm2=400.0, wind_speed_ms=2.0
    )
    assert len(warnings) == 1
    assert "Irradiance" in warnings[0]


def test_env_conditions_high_wind():
    warnings = validate_environmental_conditions(
        irradiance_wm2=700.0, wind_speed_ms=8.0
    )
    assert len(warnings) == 1
    assert "Wind" in warnings[0]


def test_env_conditions_both_bad():
    warnings = validate_environmental_conditions(
        irradiance_wm2=300.0, wind_speed_ms=10.0
    )
    assert len(warnings) == 2
