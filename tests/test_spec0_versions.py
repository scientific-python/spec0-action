import json
import runpy
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import requests


def test_generator_schedule(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "spec0_versions.py"
    monkeypatch.chdir(tmp_path)

    def now(tz=None):
        # Local time is still in Q3 while UTC has reached Q4.
        instant = pd.Timestamp("2025-09-30T17:30:00-07:00")
        return instant.tz_convert(tz) if tz else instant.tz_localize(None)

    monkeypatch.setattr(pd.Timestamp, "now", now)
    files = [
        {"filename": f"example-{version}-py3-none-any.whl", "upload-time": date}
        for version, date in [
            ("1.0.0", "2023-07-15T00:00:00.000Z"),
            ("1.1.0", "2024-01-10T00:00:00Z"),
            ("1.2.0", "2024-07-01T00:00:00Z"),
        ]
    ]
    response = Mock(json=Mock(return_value={"files": files}))
    monkeypatch.setattr(requests, "get", Mock(return_value=response))

    result = runpy.run_path(str(script))

    schedule = {
        entry["start_date"]: entry["packages"]
        for entry in json.loads((tmp_path / "schedule.json").read_text())
    }
    assert min(schedule) == "2025-07-01T00:00:00Z"
    core = result["CORE_PACKAGES"]
    assert schedule["2025-07-01T00:00:00Z"] == dict.fromkeys(core, "1.1.0")
    assert schedule["2026-01-01T00:00:00Z"] == dict.fromkeys(core, "1.2.0")
    assert schedule["2025-10-01T00:00:00Z"] == {"python": "3.12"}
    assert "gantt" in (tmp_path / "chart.md").read_text()
    assert "2026 - Quarter 1" in (tmp_path / "schedule.md").read_text()
