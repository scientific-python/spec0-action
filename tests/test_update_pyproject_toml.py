import datetime
from unittest.mock import patch

import pytest
from packaging.specifiers import SpecifierSet
from packaging.version import Version

from spec0_action.parsing import read_schedule, read_toml
from spec0_action import update_pyproject_toml
import spec0_action

# Fixed time to avoid test results changing over time
FAKE_TIME = datetime.datetime(2025, 10, 30, 0, 0, 0, tzinfo=datetime.UTC)


@pytest.fixture
def patch_datetime_now(monkeypatch):
    class mydatetime(datetime.datetime):
        @classmethod
        def now(cls, *args, **kwds):
            return FAKE_TIME

    monkeypatch.setattr(datetime, "datetime", mydatetime)


def test_update_pyproject_toml(patch_datetime_now):
    expected = read_toml("tests/test_data/pyproject_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject.toml")
    test_schedule = read_schedule("tests/test_data/test_schedule.json")
    update_pyproject_toml(pyproject_data, test_schedule)

    assert pyproject_data == expected


def test_update_pyproject_toml_with_pixi(patch_datetime_now):
    expected = read_toml("tests/test_data/pyproject_pixi_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject_pixi.toml")
    test_schedule = read_schedule("tests/test_data/test_schedule.json")
    update_pyproject_toml(pyproject_data, test_schedule)
    assert pyproject_data == expected


def _minimal_pyproject(*deps):
    return {
        "project": {
            "requires-python": ">=3.11",
            "dependencies": list(deps),
        }
    }


def test_update_all_updates_non_spec0_package(patch_datetime_now):
    pyproject = _minimal_pyproject("requests>=2.0.0", "numpy>=1.10.0")
    schedule = read_schedule("tests/test_data/test_schedule.json")
    with patch.object(
        spec0_action, "_get_oldest_version_in_window", return_value=Version("2.28.0")
    ):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    deps = pyproject["project"]["dependencies"]
    # requests is not not in SPEC 0 and should be bumped to >=2.28.0
    assert "requests>=2.28.0" in deps
    # numpy is in SPEC 0 schedule so it should be handled by spec0 logic and not the flag
    assert all("requests" not in d or "2.28.0" in d for d in deps)


def test_update_all_skips_spec0_packages(patch_datetime_now):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    schedule = read_schedule("tests/test_data/test_schedule.json")
    with patch.object(spec0_action, "_get_oldest_version_in_window") as mock_pypi:
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    # numpy is in the SPEC 0 schedule, _get_oldest_version_in_window must not be called for it
    for call_args in mock_pypi.call_args_list:
        assert call_args[0][0] != "numpy"


def test_update_all_skips_already_strict_bound(patch_datetime_now):
    pyproject = _minimal_pyproject("requests>=2.32.0")
    schedule = read_schedule("tests/test_data/test_schedule.json")
    # PyPI returns an older version than what's already pinned, therefore the bound must not regress
    with patch.object(
        spec0_action, "_get_oldest_version_in_window", return_value=Version("2.28.0")
    ):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    assert pyproject["project"]["dependencies"] == ["requests>=2.32.0"]


def test_update_all_noop_when_not_set(patch_datetime_now):
    pyproject = _minimal_pyproject("requests>=2.0.0", "numpy>=1.10.0")
    schedule = read_schedule("tests/test_data/test_schedule.json")
    with patch.object(spec0_action, "_get_oldest_version_in_window") as mock_pypi:
        update_pyproject_toml(pyproject, schedule)
    mock_pypi.assert_not_called()


def test_requires_python_preserves_existing_restrictions(patch_datetime_now):
    pyproject = _minimal_pyproject()
    pyproject["project"]["requires-python"] = ">=3.9,<3.14,!=3.13.*"
    schedule = read_schedule("tests/test_data/test_schedule.json")

    update_pyproject_toml(pyproject, schedule)

    assert SpecifierSet(pyproject["project"]["requires-python"]) == SpecifierSet(
        ">=3.12,<3.14,!=3.13.*"
    )


def test_canonical_package_names_match_schedule(patch_datetime_now):
    pyproject = _minimal_pyproject("Numpy>=1.20", "scikit_learn>=1.0")
    schedule = read_schedule("tests/test_data/test_schedule.json")

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["dependencies"] == [
        "Numpy>=2.0.0",
        "scikit_learn>=1.4.0",
    ]


def test_optional_dependencies_and_dependency_groups_are_updated(patch_datetime_now):
    pyproject = _minimal_pyproject()
    pyproject["project"]["optional-dependencies"] = {
        "test": ["Numpy>=1.20"],
    }
    pyproject["dependency-groups"] = {
        "dev": ["numpy>=1.20", {"include-group": "test"}],
    }
    schedule = read_schedule("tests/test_data/test_schedule.json")

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["optional-dependencies"]["test"] == ["Numpy>=2.0.0"]
    assert pyproject["dependency-groups"]["dev"] == [
        "numpy>=2.0.0",
        {"include-group": "test"},
    ]


def test_missing_project_dependencies_is_noop(patch_datetime_now):
    pyproject = {"project": {"requires-python": ">=3.9"}}
    schedule = read_schedule("tests/test_data/test_schedule.json")

    update_pyproject_toml(pyproject, schedule)

    assert SpecifierSet(pyproject["project"]["requires-python"]) == SpecifierSet(
        ">=3.12"
    )


def test_pixi_feature_pypi_dependencies_and_non_version_tables(patch_datetime_now):
    pyproject = _minimal_pyproject()
    pyproject["tool"] = {
        "pixi": {
            "dependencies": {
                "scikit-learn": {"git": "https://example.invalid/scikit-learn.git"}
            },
            "feature": {
                "test": {
                    "pypi-dependencies": {"Numpy": ">=1.20"},
                    "dependencies": {
                        "xarray": {"url": "https://example.invalid/pkg.whl"}
                    },
                }
            },
        }
    }
    schedule = read_schedule("tests/test_data/test_schedule.json")

    update_pyproject_toml(pyproject, schedule)

    assert (
        pyproject["tool"]["pixi"]["feature"]["test"]["pypi-dependencies"]["Numpy"]
        == ">=2.0.0"
    )
    assert pyproject["tool"]["pixi"]["dependencies"]["scikit-learn"] == {
        "git": "https://example.invalid/scikit-learn.git"
    }
    assert pyproject["tool"]["pixi"]["feature"]["test"]["dependencies"]["xarray"] == {
        "url": "https://example.invalid/pkg.whl"
    }


def test_update_all_uses_version_release_date_not_new_file_upload(
    patch_datetime_now,
):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "files": [
                    {
                        "filename": "example-1.0.0.tar.gz",
                        "upload-time": "2020-01-01T00:00:00Z",
                    },
                    {
                        "filename": "example-1.0.0-py3-none-any.whl",
                        "upload-time": "2025-01-01T00:00:00Z",
                    },
                    {
                        "filename": "example-2.0.0-py3-none-any.whl",
                        "upload-time": "2024-01-01T00:00:00Z",
                    },
                ]
            }

    with patch.object(spec0_action.requests, "get", return_value=Response()):
        assert spec0_action._get_oldest_version_in_window("example", 2) == Version(
            "2.0.0"
        )
