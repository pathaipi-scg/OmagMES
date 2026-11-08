from __future__ import annotations

from datetime import datetime
from typing import Any


MOCK_OBSERVATIONS = [
    {"tag": "ProductCnt", "time": "2026-11-08T06:55:00+07:00", "value": 4870},
    {"tag": "ProductCnt", "time": "2026-11-08T07:05:00+07:00", "value": 35},
    {"tag": "ProductCnt", "time": "2026-11-08T07:10:00+07:00", "value": 84},
    {"tag": "ProductCnt", "time": "2026-11-08T11:00:00+07:00", "value": 820},
    {"tag": "CYC", "time": "2026-11-08T11:00:00+07:00", "value": 3},
]
MOCK_REJECT_COUNTERS = {"cntR1": 12, "cntR2": 7, "cntR3": 3}
MOCK_WET_CAMERA_PIECES = 742


def preview_autocal() -> dict[str, Any]:
    """Return deterministic mock suggestions; never writes to the store."""
    product_cnt = [row for row in MOCK_OBSERVATIONS if row["tag"] == "ProductCnt"]
    pre_reset = next(row for row in product_cnt if row["time"].startswith("2026-11-08T06"))
    post_reset = next(row for row in product_cnt if row["time"].startswith("2026-11-08T07:05"))
    latest = next(row for row in product_cnt if row["time"].startswith("2026-11-08T11"))
    first_after_reset = datetime.fromisoformat(post_reset["time"])
    latest_at = datetime.fromisoformat(latest["time"])
    # The first post-reset value is the known daily count since the 07:00 reset.
    drops = post_reset["value"] + (latest["value"] - post_reset["value"])
    reject_counters = dict(MOCK_REJECT_COUNTERS)
    return {
        "mode": "MOCK SUGGESTION — not persisted",
        "suggested_actual_drops": drops,
        "suggested_wet_good_pieces": MOCK_WET_CAMERA_PIECES,
        "suggested_wet_rejects": reject_counters,
        "reject_total": sum(reject_counters.values()),
        "raw_observations": MOCK_OBSERVATIONS,
        "source_notes": [
            "ProductCnt is the quantity source; CYC is excluded.",
            "The 07:00 Asia/Bangkok daily reset is treated as an explicit counter boundary.",
            "The pre-reset to post-reset delta is not summed; the first post-reset reading establishes the new daily baseline.",
            "Wet camera values are individual tray Pieces from line='wet'.",
            "Dynamic cntR* quantities are shown; R* binary button states are not used.",
            f"Mock window: {first_after_reset.isoformat()} to {latest_at.isoformat()}.",
        ],
    }
