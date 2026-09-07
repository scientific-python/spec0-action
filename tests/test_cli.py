import datetime
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from packaging.version import Version

import spec0_action
from spec0_action import read_toml

SCRIPT = Path(__file__).resolve().parents[1] / "run_spec0_update.py"
SCHEDULE = '[{"start_date": "2000-01-01T00:00:00Z", "packages": {"numpy": "2.0", "python": "3.12", "scikit-learn": "1.4", "pandas": "2.2"}}]'
PROJECT = '[project]\nrequires-python = ">= 3.9"\ndependencies = ["numpy >= 1.26", "scikit-learn >= 1.0", "pandas>=1.0"]\n'


@pytest.mark.parametrize(
    ("excluded", "requires_python", "dependencies"),
    [
        ("", ">=3.12", ["numpy>=2.0", "scikit-learn>=1.4", "pandas>=2.2"]),
        (
            "numpy, PYTHON\nscikit-learn",
            ">= 3.9",
            ["numpy >= 1.26", "scikit-learn >= 1.0", "pandas>=2.2"],
        ),
    ],
)
def test_cli_excluded_packages(
    tmp_path, monkeypatch, excluded, requires_python, dependencies
):
    project = tmp_path / "pyproject.toml"
    project.write_text(PROJECT)
    schedule = tmp_path / "schedule.json"
    schedule.write_text(SCHEDULE)
    argv = [str(SCRIPT), str(project), str(schedule), "--excluded-packages", excluded]
    monkeypatch.setattr(sys, "argv", argv)

    runpy.run_path(str(SCRIPT), run_name="__main__")

    assert read_toml(project)["project"] == {
        "requires-python": requires_python,
        "dependencies": dependencies,
    }


def test_cli_invalid_exclusion_preserves_file(tmp_path, monkeypatch):
    project = tmp_path / "pyproject.toml"
    project.write_text(PROJECT)
    schedule = tmp_path / "schedule.json"
    schedule.write_text(SCHEDULE)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(SCRIPT), str(project), str(schedule), "--excluded-packages", "numpy>=1"],
    )

    with pytest.raises(ValueError, match="invalid"):
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert project.read_bytes() == PROJECT.encode()


def test_cli_custom_support_period(tmp_path, monkeypatch):
    project = tmp_path / "pyproject.toml"
    project.write_text(PROJECT)
    schedule = tmp_path / "schedule.json"
    schedule.write_text(SCHEDULE)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            str(project),
            str(schedule),
            "--spec0-support-years",
            "3",
            "--update-all",
            "2",
            "--excluded-packages",
            "pandas,\nscikit-learn",
        ],
    )

    with (
        patch.object(
            spec0_action, "_get_spec0_floor", return_value=Version("1.27")
        ) as floor,
        patch.object(spec0_action, "_get_oldest_version_in_window") as fallback,
    ):
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert read_toml(project)["project"] == {
        "requires-python": ">=3.12",
        "dependencies": ["numpy>=1.27", "scikit-learn >= 1.0", "pandas>=1.0"],
    }
    floor.assert_called_once()
    assert floor.call_args.args[:2] == ("numpy", datetime.timedelta(days=1095))
    fallback.assert_not_called()


@pytest.mark.parametrize("value", ["invalid", "0"])
def test_cli_invalid_support_period_preserves_file(tmp_path, monkeypatch, value):
    project = tmp_path / "pyproject.toml"
    project.write_text(PROJECT)
    schedule = tmp_path / "schedule.json"
    schedule.write_text(SCHEDULE)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            str(project),
            str(schedule),
            "--spec0-support-years",
            value,
        ],
    )

    with (
        pytest.raises((ValueError, SystemExit)),
        patch.object(spec0_action.requests, "get") as get,
    ):
        runpy.run_path(str(SCRIPT), run_name="__main__")

    assert project.read_bytes() == PROJECT.encode()
    get.assert_not_called()
