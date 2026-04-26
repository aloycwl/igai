from __future__ import annotations

from typing import Any, Dict


def to_embedding_text(record: Dict[str, Any]) -> str:
    """Convert normalized health record to stable embedding text."""

    def val(key: str) -> Any:
        value = record.get(key)
        return "unknown" if value is None else value

    lines = [
        f"User ID {val('user_id')}",
        f"Timestamp {val('timestamp')}",
        f"Heart rate {val('heart_rate')} bpm",
        f"SpO2 {val('spo2')} percent",
        f"Respiratory rate {val('respiratory_rate')} breaths/min",
        f"Stress score {val('stress_score')}",
        f"HRV SDNN {val('hrv_sdnn')} ms",
        f"HRV RMSSD {val('hrv_rmssd')} ms",
        f"Systolic blood pressure {val('systolic_bp')} mmHg",
        f"Diastolic blood pressure {val('diastolic_bp')} mmHg",
        f"Cardiovascular risk {val('cardiovascular_risk')}",
        f"Stroke risk {val('stroke_risk')}",
        f"General wellness {val('general_wellness')}",
    ]
    return ". ".join(lines) + "."
