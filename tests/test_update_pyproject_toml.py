import datetime
from unittest.mock import patch

import pytest
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


@pytest.fixture
def schedule():
    return read_schedule("tests/test_data/test_schedule.json")


@pytest.fixture(autouse=True)
def clear_pypi_cache():
    spec0_action._get_oldest_version_in_window.cache_clear()


def _minimal_pyproject(*deps):
    return {
        "project": {
            "requires-python": ">=3.11",
            "dependencies": list(deps),
        }
    }


def _mock_pypi(version=None):
    kwargs = {"return_value": Version(version)} if version else {}
    return patch.object(spec0_action, "_get_oldest_version_in_window", **kwargs)


def _pypi_response(files):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"files": files}

    return Response()


def test_update_pyproject_toml(patch_datetime_now, schedule):
    expected = read_toml("tests/test_data/pyproject_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject.toml")
    update_pyproject_toml(pyproject_data, schedule)

    assert pyproject_data == expected


def test_update_pyproject_toml_with_pixi(patch_datetime_now, schedule):
    expected = read_toml("tests/test_data/pyproject_pixi_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject_pixi.toml")
    update_pyproject_toml(pyproject_data, schedule)
    assert pyproject_data == expected


def test_update_all_updates_non_spec0_package(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("requests>=2.0.0", "numpy>=1.10.0")
    with _mock_pypi("2.28.0"):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    # requests is not in SPEC 0 and is bumped from PyPI, numpy from the schedule
    assert pyproject["project"]["dependencies"] == [
        "requests>=2.28.0",
        "numpy>=2.0.0",
    ]


def test_update_all_skips_spec0_packages(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    with _mock_pypi() as mock_pypi:
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    # numpy is in the SPEC 0 schedule, PyPI must not be queried for it
    mock_pypi.assert_not_called()


def test_update_all_skips_already_strict_bound(patch_datetime_now, schedule):
    # PyPI returns an older version than what's already pinned, the bound must not regress
    pyproject = _minimal_pyproject("requests>=2.32.0")
    with _mock_pypi("2.28.0"):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)
    assert pyproject["project"]["dependencies"] == ["requests>=2.32.0"]


def test_update_all_noop_when_not_set(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("requests>=2.0.0", "numpy>=1.10.0")
    with _mock_pypi() as mock_pypi:
        update_pyproject_toml(pyproject, schedule)
    mock_pypi.assert_not_called()


def test_update_all_updates_optional_dependency_groups_and_unbounded(
    patch_datetime_now, schedule
):
    pyproject = _minimal_pyproject("requests")
    pyproject["project"]["optional-dependencies"] = {
        "test": ["idna>=3.0.0"],
    }
    pyproject["dependency-groups"] = {
        "dev": ["charset-normalizer>=3.0.0", {"include-group": "test"}],
    }
    with _mock_pypi("9.0.0"):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    assert pyproject["project"]["dependencies"] == ["requests>=9.0.0"]
    assert pyproject["project"]["optional-dependencies"]["test"] == ["idna>=9.0.0"]
    assert pyproject["dependency-groups"]["dev"] == [
        "charset-normalizer>=9.0.0",
        {"include-group": "test"},
    ]


def test_self_referencing_extras_are_left_alone(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("requests>=2.0.0")
    pyproject["project"]["name"] = "My_Package"
    pyproject["dependency-groups"] = {
        "tests": ["my-package[plotting,tests-only]"],
    }
    with _mock_pypi("2.2.2") as mock_pypi:
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    assert pyproject["dependency-groups"]["tests"] == [
        "my-package[plotting,tests-only]"
    ]
    for call_args in mock_pypi.call_args_list:
        assert call_args[0][0] != "my-package"


def test_self_reference_skipped_even_when_in_schedule(patch_datetime_now, schedule):
    # A project named like a schedule package must not have its self-reference pinned
    pyproject = _minimal_pyproject("numpy[test]")
    pyproject["project"]["name"] = "numpy"

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["dependencies"] == ["numpy[test]"]


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        # tightened to the schedule floor, other restrictions kept
        (">=3.9,<3.14,!=3.13.*", ">=3.12,<3.14,!=3.13.*"),
        # missing: the schedule floor is added
        (None, ">=3.12"),
        # incompatible: preserved byte-exact, not rewritten in normalized form
        (">= 3.9, < 3.12", ">= 3.9, < 3.12"),
        # unparseable (poetry-style): left alone
        ("^3.10", "^3.10"),
    ],
)
def test_requires_python(patch_datetime_now, schedule, current, expected):
    pyproject = _minimal_pyproject()
    if current is None:
        del pyproject["project"]["requires-python"]
    else:
        pyproject["project"]["requires-python"] = current

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["requires-python"] == expected


def test_missing_project_dependencies_is_noop(patch_datetime_now, schedule):
    pyproject = {"project": {"requires-python": ">=3.9"}}

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["requires-python"] == ">=3.12"


def test_canonical_package_names_match_schedule(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("Numpy>=1.20", "scikit_learn>=1.0")

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["dependencies"] == [
        "Numpy>=2.0.0",
        "scikit_learn>=1.4.0",
    ]


def test_optional_dependencies_and_dependency_groups_are_updated(
    patch_datetime_now, schedule
):
    pyproject = _minimal_pyproject()
    pyproject["project"]["optional-dependencies"] = {
        "test": ["Numpy>=1.20"],
    }
    pyproject["dependency-groups"] = {
        "dev": ["numpy>=1.20", {"include-group": "test"}],
    }

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"]["optional-dependencies"]["test"] == ["Numpy>=2.0.0"]
    assert pyproject["dependency-groups"]["dev"] == [
        "numpy>=2.0.0",
        {"include-group": "test"},
    ]


def test_url_pinned_and_up_to_date_dependencies_left_untouched(
    patch_datetime_now, schedule
):
    deps = [
        "scipy @ https://example.invalid/scipy.whl",  # url dependency
        "numpy==1.21.0",  # pin conflicting with the schedule
        "xarray >= 2024.1.0",  # already at the schedule floor
    ]
    pyproject = _minimal_pyproject(*deps)

    update_pyproject_toml(pyproject, schedule)

    # All preserved byte-exact, including original whitespace
    assert pyproject["project"]["dependencies"] == deps


def test_pixi_feature_pypi_dependencies_and_non_version_tables(
    patch_datetime_now, schedule
):
    pyproject = _minimal_pyproject()
    pyproject["tool"] = {
        "pixi": {
            "dependencies": {
                "scikit-learn": {"git": "https://example.invalid/scikit-learn.git"},
                "pandas": {"version": ">=1.0", "channel": "conda-forge"},
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

    update_pyproject_toml(pyproject, schedule)

    pixi = pyproject["tool"]["pixi"]
    assert pixi["feature"]["test"]["pypi-dependencies"]["Numpy"] == ">=2.0.0"
    # version tables are updated in place, other keys kept
    assert pixi["dependencies"]["pandas"] == {
        "version": ">=2.2.0",
        "channel": "conda-forge",
    }
    # git and url dependencies are not touched
    assert pixi["dependencies"]["scikit-learn"] == {
        "git": "https://example.invalid/scikit-learn.git"
    }
    assert pixi["feature"]["test"]["dependencies"]["xarray"] == {
        "url": "https://example.invalid/pkg.whl"
    }


def test_pixi_target_dependencies_are_updated(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject()
    pyproject["tool"] = {
        "pixi": {
            "target": {"linux-64": {"dependencies": {"numpy": ">=1.20"}}},
            "feature": {
                "test": {
                    "target": {"osx-arm64": {"pypi-dependencies": {"numpy": ">=1.20"}}}
                }
            },
        }
    }

    update_pyproject_toml(pyproject, schedule)

    pixi = pyproject["tool"]["pixi"]
    assert pixi["target"]["linux-64"]["dependencies"]["numpy"] == ">=2.0.0"
    assert (
        pixi["feature"]["test"]["target"]["osx-arm64"]["pypi-dependencies"]["numpy"]
        == ">=2.0.0"
    )


def test_update_all_uses_version_release_date_not_new_file_upload(patch_datetime_now):
    response = _pypi_response(
        [
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
    )

    with patch.object(spec0_action.requests, "get", return_value=response):
        assert spec0_action._get_oldest_version_in_window("example", 2) == Version(
            "2.0.0"
        )


def test_update_all_queries_pypi_once_per_package(patch_datetime_now, schedule):
    requested_urls = []

    def fake_get(url, **kwargs):
        requested_urls.append(url)
        return _pypi_response(
            [
                {
                    "filename": "demo_pkg-2.0.0-py3-none-any.whl",
                    "upload-time": "2025-01-01T00:00:00Z",
                }
            ]
        )

    pyproject = _minimal_pyproject("Demo_Pkg>=1.0.0")
    pyproject["dependency-groups"] = {"dev": ["demo-pkg>=1.0.0"]}

    with patch.object(spec0_action.requests, "get", side_effect=fake_get):
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    # Both spellings canonicalize to demo-pkg and share one PyPI request
    assert requested_urls == ["https://pypi.org/simple/demo-pkg"]
    assert pyproject["project"]["dependencies"] == ["Demo_Pkg>=2.0.0"]
    assert pyproject["dependency-groups"]["dev"] == ["demo-pkg>=2.0.0"]
