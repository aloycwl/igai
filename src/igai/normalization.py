from __future__ import annotations

from typing import Any, Dict, Optional


NORMALIZED_SCHEMA = (
    "user_id",
    "timestamp",
    "heart_rate",
    "spo2",
    "respiratory_rate",
    "stress_score",
    "hrv_sdnn",
    "hrv_rmssd",
    "systolic_bp",
    "diastolic_bp",
    "cardiovascular_risk",
    "stroke_risk",
    "general_wellness",
)


def normalize_record(json_data: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Flatten a raw health JSON payload into PostgreSQL-ready fields."""
    vital = json_data.get("vitalSigns") or {}
    holistic = json_data.get("holisticHealth") or {}
    risks = json_data.get("risks") or {}
    cardio_risks = risks.get("cardiovascularRisks") or {}

    systolic = vital.get("bloodPressureSystolic")
    diastolic = vital.get("bloodPressureDiastolic")

    if systolic is None or diastolic is None:
        bp_raw = vital.get("bloodPressure")
        if isinstance(bp_raw, str) and "/" in bp_raw:
            left, right = bp_raw.split("/", 1)
            left = left.strip()
            right = right.strip()
            if systolic is None and left.isdigit():
                systolic = int(left)
            if diastolic is None and right.isdigit():
                diastolic = int(right)

    return {
        "user_id": json_data.get("user_id"),
        "timestamp": json_data.get("timestamp"),
        "heart_rate": vital.get("heartRate"),
        "spo2": vital.get("spo2"),
        "respiratory_rate": vital.get("respiratoryRate"),
        "stress_score": vital.get("stressScore"),
        "hrv_sdnn": vital.get("hrvSdnn"),
        "hrv_rmssd": vital.get("hrvRmssd"),
        "systolic_bp": systolic,
        "diastolic_bp": diastolic,
        "cardiovascular_risk": cardio_risks.get("generalRisk"),
        "stroke_risk": cardio_risks.get("stroke"),
        "general_wellness": holistic.get("generalWellness"),
    }
