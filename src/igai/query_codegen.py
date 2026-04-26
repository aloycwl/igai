from __future__ import annotations

import re


def generate_analysis_script(query: str) -> str:
    """Generate a safe local pandas analysis script for supported query patterns."""
    q = (query or "").strip().lower()

    trend_pattern = any(k in q for k in ["trend", "over time", "last 7 days", "last 30 days", "time"])
    comparison_pattern = any(k in q for k in ["compare", "comparison", "cohort", "group by"])
    agg_match = re.search(r"(average|avg|max|maximum|min|minimum)\s+([a-zA-Z_ ]+)", q)

    metric = "heart_rate"
    candidates = [
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
    ]

    for candidate in candidates:
        if candidate in q:
            metric = candidate
            break
    if metric == "heart_rate" and "heart rate" in q:
        metric = "heart_rate"

    if comparison_pattern:
        return f'''import pandas as pd
import matplotlib.pyplot as plt

# expects existing dataframe: df
df = df.copy()
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp", "{metric}"])

cohort_col = "cohort" if "cohort" in df.columns else "user_id"
grouped = (
    df.groupby(cohort_col)["{metric}"]
    .mean()
    .sort_values(ascending=False)
)

ax = grouped.plot(kind="bar", figsize=(10, 5), title="Average {metric} by " + cohort_col)
ax.set_xlabel(cohort_col)
ax.set_ylabel("Average {metric}")
plt.tight_layout()
plt.show()
'''

    if agg_match:
        agg_word = agg_match.group(1)
        agg_func = "mean"
        agg_label = "Average"
        if agg_word in {"max", "maximum"}:
            agg_func = "max"
            agg_label = "Maximum"
        elif agg_word in {"min", "minimum"}:
            agg_func = "min"
            agg_label = "Minimum"

        return f'''import pandas as pd
import matplotlib.pyplot as plt

# expects existing dataframe: df
df = df.copy()
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp", "{metric}"])
df["date"] = df["timestamp"].dt.date

daily = (
    df.groupby("date")["{metric}"]
    .{agg_func}()
    .reset_index(name="{metric}_{agg_func}")
)

ax = daily.plot(x="date", y="{metric}_{agg_func}", kind="line", marker="o", figsize=(10, 5),
                title="{agg_label} {metric} over time")
ax.set_xlabel("Date")
ax.set_ylabel("{agg_label} {metric}")
plt.tight_layout()
plt.show()
'''

    if trend_pattern:
        return f'''import pandas as pd
import matplotlib.pyplot as plt

# expects existing dataframe: df
df = df.copy()
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp", "{metric}"])

end_ts = df["timestamp"].max()
start_ts = end_ts - pd.Timedelta(days=7)
recent = df[df["timestamp"].between(start_ts, end_ts)].copy()
recent["date"] = recent["timestamp"].dt.date

daily_avg = (
    recent.groupby("date")["{metric}"]
    .mean()
    .reset_index(name="{metric}_avg")
)

ax = daily_avg.plot(x="date", y="{metric}_avg", kind="line", marker="o", figsize=(10, 5),
                    title="Average {metric} trend over last 7 days")
ax.set_xlabel("Date")
ax.set_ylabel("Average {metric}")
plt.tight_layout()
plt.show()
'''

    return '''import pandas as pd
import matplotlib.pyplot as plt

# expects existing dataframe: df
df = df.copy()
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
df = df.dropna(subset=["timestamp", "heart_rate"])
df["date"] = df["timestamp"].dt.date

daily_avg = (
    df.groupby("date")["heart_rate"]
    .mean()
    .reset_index(name="heart_rate_avg")
)

ax = daily_avg.plot(x="date", y="heart_rate_avg", kind="line", marker="o", figsize=(10, 5),
                    title="Average heart rate over time")
ax.set_xlabel("Date")
ax.set_ylabel("Average heart rate")
plt.tight_layout()
plt.show()
'''
