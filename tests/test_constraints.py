import datetime
import json
import runpy
from pathlib import Path

import pytest
from packaging.version import Version

from spec0_action import read_schedule
from spec0_action.constraints import (
    ScheduleError,
    format_constraints,
    minimum_versions,
    parse_package_list,
    schedule_floors,
)

ROOT = Path(__file__).resolve().parents[1]
main = runpy.run_path(str(ROOT / "run_spec0_constraints.py"))["main"]
TEST_SCHEDULE = ROOT / "tests" / "test_data" / "test_schedule.json"
SCHEDULE = [
    {
        "start_date": "2025-01-01T00:00:00Z",
        "packages": {"numpy": "2.0.0", "pandas": "2.2.0", "python": "3.12"},
    },
    {
        "start_date": "2025-04-01T00:00:00Z",
        "packages": {"numpy": "2.1.0", "scikit-learn": "1.5.0"},
    },
    {
        "start_date": "2025-07-01T00:00:00Z",
        "packages": {"Scikit_Learn": "1.6.0", "python": "3.13"},
    },
]


def utc(year, month, day):
    return datetime.datetime(year, month, day, tzinfo=datetime.UTC)


def test_floors_combine_all_entries_up_to_the_date():
    floors = schedule_floors(SCHEDULE, utc(2025, 5, 15))
    # numpy was raised in the second entry, pandas and python only appear in the first
    assert floors == {
        "numpy": Version("2.1.0"),
        "pandas": Version("2.2.0"),
        "python": Version("3.12"),
        "scikit-learn": Version("1.5.0"),
    }


def test_entry_applies_from_its_start_date():
    assert schedule_floors(SCHEDULE, utc(2025, 6, 30))["python"] == Version("3.12")
    assert schedule_floors(SCHEDULE, utc(2025, 7, 1))["python"] == Version("3.13")


def test_unsorted_schedule_and_naive_date():
    floors = schedule_floors(list(reversed(SCHEDULE)), datetime.datetime(2025, 8, 1))
    assert floors["scikit-learn"] == Version("1.6.0")
    assert floors["numpy"] == Version("2.1.0")


def test_nothing_applies_before_the_first_entry():
    assert schedule_floors(SCHEDULE, utc(2024, 12, 31)) == {}


def test_minimum_versions_keeps_requested_order():
    versions = minimum_versions(SCHEDULE, "scikit-learn, numpy", utc(2025, 8, 1))
    assert list(versions) == ["scikit-learn", "numpy"]


def test_missing_floor_lists_every_missing_package():
    with pytest.raises(ScheduleError, match="matplotlib, scipy"):
        minimum_versions(SCHEDULE, "numpy matplotlib scipy", utc(2025, 8, 1))


def test_floor_not_yet_in_effect_is_missing():
    with pytest.raises(ScheduleError, match="scikit-learn"):
        minimum_versions(SCHEDULE, "scikit-learn", utc(2025, 2, 1))


def test_no_packages_requested():
    with pytest.raises(ScheduleError, match="no packages"):
        minimum_versions(SCHEDULE, " , ", utc(2025, 8, 1))


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        ({"packages": {}}, "list"),
        ([{"start_date": "2025-01-01"}], "no packages mapping"),
        ([{"packages": {"numpy": "2.0"}}], "start_date"),
        ([{"start_date": "soon", "packages": {}}], "start_date"),
        (
            [{"start_date": "2025-01-01", "packages": {"numpy": "two"}}],
            "invalid version",
        ),
    ],
)
def test_invalid_schedule(schedule, message):
    with pytest.raises(ScheduleError, match=message):
        schedule_floors(schedule, utc(2025, 8, 1))


def test_package_list_is_normalized_and_deduplicated():
    assert parse_package_list("NumPy,scikit_learn  numpy\nscipy") == [
        "numpy",
        "scikit-learn",
        "scipy",
    ]


def test_constraints_are_exact_pins_without_python():
    versions = minimum_versions(SCHEDULE, "python numpy pandas", utc(2025, 8, 1))
    assert format_constraints(versions) == "numpy==2.1.0\npandas==2.2.0\n"


def test_cli_writes_constraints_and_github_outputs(tmp_path, monkeypatch, capsys):
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps(SCHEDULE))
    output = tmp_path / "constraints.txt"
    github_output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))

    code = main(
        [
            str(schedule),
            "--packages",
            "numpy pandas python",
            "--output",
            str(output),
            "--reference-date",
            "2025-08-01",
        ]
    )

    assert code == 0
    assert output.read_text() == "numpy==2.1.0\npandas==2.2.0\n"
    outputs = dict(
        line.split("=", 1) for line in github_output.read_text().splitlines()
    )
    assert outputs["constraints_file"] == str(output)
    assert json.loads(outputs["versions"]) == {
        "numpy": "2.1.0",
        "pandas": "2.2.0",
        "python": "3.13",
    }
    assert outputs["python_version"] == "3.13"
    assert "numpy==2.1.0" in capsys.readouterr().out


def test_cli_fails_clearly_on_missing_floor(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps(SCHEDULE))
    output = tmp_path / "constraints.txt"

    code = main(
        [
            str(schedule),
            "--packages",
            "numpy zarr",
            "--output",
            str(output),
            "--reference-date",
            "2025-08-01",
        ]
    )

    assert code == 1
    assert "zarr" in capsys.readouterr().err
    assert not output.exists()


def test_cli_rejects_bad_reference_date(tmp_path):
    schedule = tmp_path / "schedule.json"
    schedule.write_text(json.dumps(SCHEDULE))
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        main([str(schedule), "--packages", "numpy", "--reference-date", "01.08.2025"])


def test_bundled_test_schedule():
    versions = minimum_versions(
        read_schedule(TEST_SCHEDULE), "numpy scipy pandas", utc(2025, 4, 1)
    )
    assert format_constraints(versions) == (
        "numpy==1.26.0\nscipy==1.12.0\npandas==2.1.0\n"
    )
