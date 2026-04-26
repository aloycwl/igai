from __future__ import annotations

from typing import Any, Dict, List


def build_health_report(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Build a cautious, non-diagnostic report from aggregated metrics."""
    summary_parts: List[str] = []
    key_observations: List[str] = []
    potential_concerns: List[str] = []
    positive_signals: List[str] = []

    hr_avg = metrics.get("heart_rate_avg")
    spo2_avg = metrics.get("spo2_avg")
    stress_avg = metrics.get("stress_score_avg")
    cardio_risk_avg = metrics.get("cardiovascular_risk_avg")
    wellness_avg = metrics.get("general_wellness_avg")

    if hr_avg is not None:
        key_observations.append(f"Average heart rate was {hr_avg}.")
        if hr_avg > 100:
            potential_concerns.append("Average heart rate appears elevated in this period.")
        elif 60 <= hr_avg <= 90:
            positive_signals.append(
                "Average heart rate was within a commonly expected resting range for many adults."
            )

    if spo2_avg is not None:
        key_observations.append(f"Average SpO2 was {spo2_avg}.")
        if spo2_avg < 95:
            potential_concerns.append("Average oxygen saturation was lower than commonly observed values.")
        else:
            positive_signals.append("Average oxygen saturation remained in a generally favorable range.")

    if stress_avg is not None:
        key_observations.append(f"Average stress score was {stress_avg}.")
        if stress_avg >= 70:
            potential_concerns.append("Stress levels were frequently high based on the provided score.")
        elif stress_avg <= 40:
            positive_signals.append("Stress scores were generally on the lower side.")

    if cardio_risk_avg is not None:
        key_observations.append(f"Average cardiovascular risk score was {cardio_risk_avg}.")
        if cardio_risk_avg >= 7:
            potential_concerns.append(
                "Cardiovascular risk indicators were relatively elevated in this dataset."
            )

    if wellness_avg is not None:
        key_observations.append(f"Average general wellness score was {wellness_avg}.")
        if wellness_avg >= 75:
            positive_signals.append("General wellness scores were consistently strong.")
        elif wellness_avg < 50:
            potential_concerns.append("General wellness scores trended lower across the observed period.")

    if not key_observations:
        summary_parts.append("Limited aggregated metrics were provided.")
    else:
        summary_parts.append("This report summarizes recent aggregated health indicators from the provided data.")

    if potential_concerns:
        summary_parts.append("Some metrics may benefit from closer follow-up over time.")
    if positive_signals:
        summary_parts.append("Several indicators were stable or favorable.")

    return {
        "summary": " ".join(summary_parts),
        "key_observations": key_observations,
        "potential_concerns": potential_concerns,
        "positive_signals": positive_signals,
    }
