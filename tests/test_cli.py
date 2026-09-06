import runpy
import sys
from pathlib import Path

import pytest

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
