import json
import subprocess
import sys
from pathlib import Path

import pytest

from spec0_action import read_toml


@pytest.mark.parametrize(
    "excluded_packages",
    ["numpy, PYTHON\nscikit-learn", "numpy>=1", "numpy[extra]", "numpy*"],
)
def test_cli_excluded_packages(tmp_path, excluded_packages):
    project_path = tmp_path / "pyproject.toml"
    original = """[project]
requires-python = ">= 3.9"
dependencies = ["numpy >= 1.26", "scikit-learn >= 1.0", "pandas>=1.0"]
"""
    project_path.write_text(original)
    schedule_path = tmp_path / "schedule.json"
    schedule_path.write_text(
        json.dumps(
            [
                {
                    "start_date": "2000-01-01T00:00:00Z",
                    "packages": {
                        "numpy": "2.0",
                        "python": "3.12",
                        "scikit-learn": "1.4",
                        "pandas": "2.2",
                    },
                }
            ]
        )
    )

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "run_spec0_update.py"),
            str(project_path),
            str(schedule_path),
            "--excluded-packages",
            excluded_packages,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if excluded_packages.startswith("numpy,"):
        assert result.returncode == 0, result.stderr
        assert read_toml(project_path)["project"] == {
            "requires-python": ">= 3.9",
            "dependencies": ["numpy >= 1.26", "scikit-learn >= 1.0", "pandas>=2.2"],
        }
    else:
        assert result.returncode != 0
        assert "name is invalid" in result.stderr
        assert project_path.read_text() == original
