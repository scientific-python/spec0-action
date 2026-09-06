import json
import runpy
from datetime import UTC, timedelta
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import requests
from packaging.version import Version


def test_generator_uses_utc_dates_and_preserves_quarter_schedule(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / "spec0_versions.py"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        pd.Timestamp, "now", lambda tz=None: pd.Timestamp("2025-10-30", tz=tz)
    )
    files = [
        {"filename": f"example-{version}-py3-none-any.whl", "upload-time": date}
        for version, date in [
            ("1.0.0", "2023-07-15T00:00:00.000Z"),
            ("1.1.0", "2024-01-10T00:00:00Z"),
            ("1.2.0", "2024-07-01T00:00:00Z"),
        ]
    ]
    get = Mock(return_value=Mock(json=Mock(return_value={"files": files})))
    monkeypatch.setattr(requests, "get", get)

    result = runpy.run_path(str(script))

    assert get.call_count == len(result["CORE_PACKAGES"])
    assert result["CUTOFF"] == pd.Timestamp("2025-01-01", tz=UTC)
    for releases in result["package_releases"].values():
        for dates in releases.values():
            assert dates["release_date"].utcoffset() == timedelta(0)
            assert dates["drop_date"].utcoffset() == timedelta(0)
    assert result["package_releases"]["numpy"][Version("1.0.0")][
        "release_date"
    ] == pd.Timestamp("2023-07-15", tz=UTC)
    schedule = {
        entry["start_date"]: entry["packages"]
        for entry in json.loads((tmp_path / "schedule.json").read_text())
    }
    assert schedule["2025-07-01T00:00:00Z"] == {
        package: "1.1.0" for package in result["CORE_PACKAGES"]
    }
    assert schedule["2026-01-01T00:00:00Z"] == {
        package: "1.2.0" for package in result["CORE_PACKAGES"]
    }
    assert schedule["2025-10-01T00:00:00Z"] == {"python": "3.12"}
    assert "gantt" in (tmp_path / "chart.md").read_text()
    assert "2026 - Quarter 1" in (tmp_path / "schedule.md").read_text()
