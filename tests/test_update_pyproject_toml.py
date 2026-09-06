import datetime
from copy import deepcopy
from unittest.mock import Mock, call, patch

import pytest
from packaging.version import Version

import spec0_action
from spec0_action import update_pyproject_toml
from spec0_action.parsing import read_schedule, read_toml

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
    return Mock(json=Mock(return_value={"files": files}))


@pytest.mark.parametrize("name", ["pyproject", "pyproject_pixi"])
def test_update_pyproject_toml(patch_datetime_now, schedule, name):
    pyproject = read_toml(f"tests/test_data/{name}.toml")
    update_pyproject_toml(pyproject, schedule)
    assert pyproject == read_toml(f"tests/test_data/{name}_updated.toml")


@pytest.mark.parametrize(
    ("update_all", "expected"), [(None, "requests>=2.0.0"), (2.0, "requests>=2.28.0")]
)
def test_update_all_controls_pypi_fallback(
    patch_datetime_now, schedule, update_all, expected
):
    # Non-SPEC 0 packages come from PyPI only when update_all is set; schedule
    # packages never do, and keep their original spelling
    pyproject = _minimal_pyproject(
        "requests>=2.0.0", "Numpy>=1.10.0", "scikit_learn>=1.0"
    )
    with _mock_pypi("2.28.0") as mock_pypi:
        update_pyproject_toml(pyproject, schedule, update_all=update_all)
    assert mock_pypi.call_args_list == ([call("requests", 2.0)] if update_all else [])
    assert pyproject["project"]["dependencies"] == [
        expected,
        "Numpy>=2.0.0",
        "scikit_learn>=1.4.0",
    ]


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


@pytest.mark.parametrize("name", ["My_Package", "numpy", "Python"])
def test_self_reference_left_alone(patch_datetime_now, schedule, name):
    # Self-references like "pkg[extras]" share extras between groups; never pin
    # them, even with update_all or when the project is named like a schedule package
    dep = f"{name.lower()}[plotting,tests-only]"
    pyproject = _minimal_pyproject("requests>=2.0.0", dep)
    pyproject["project"]["name"] = name
    with _mock_pypi("2.2.2") as mock_pypi:
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    mock_pypi.assert_called_once_with("requests", 2.0)
    assert pyproject["project"]["dependencies"] == ["requests>=2.2.2", dep]
    assert pyproject["project"]["requires-python"] == ">=3.12"


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        # tightened to the schedule floor, other restrictions kept
        (">=3.9,<3.14,!=3.13.*", ">=3.12,<3.14,!=3.13.*"),
        # missing: the schedule floor is added
        (None, ">=3.12"),
        # incompatible: preserved byte-exact, not rewritten in normalized form
        (">= 3.9, < 3.12", ">= 3.9, < 3.12"),
        # unparsable (poetry-style): left alone
        ("^3.10", "^3.10"),
    ],
)
def test_requires_python(patch_datetime_now, schedule, current, expected):
    # No dependencies table at all: only requires-python is touched
    pyproject = {"project": {}}
    if current:
        pyproject["project"]["requires-python"] = current

    update_pyproject_toml(pyproject, schedule)

    assert pyproject["project"] == {"requires-python": expected}


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


@pytest.mark.parametrize(
    ("stage", "error"),
    [
        ("get", spec0_action.requests.ConnectionError("offline")),
        ("raise_for_status", spec0_action.requests.HTTPError("server error")),
        (
            "json",
            spec0_action.requests.exceptions.JSONDecodeError("invalid JSON", "", 0),
        ),
    ],
)
def test_update_all_preserves_dependency_on_pypi_failure(
    patch_datetime_now, schedule, stage, error
):
    pyproject = _minimal_pyproject("requests >= 2.0")
    with patch.object(spec0_action.requests, "get") as get:
        operation = get if stage == "get" else getattr(get.return_value, stage)
        operation.side_effect = error
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    assert pyproject["project"]["dependencies"] == ["requests >= 2.0"]


def test_update_all_queries_pypi_once_per_package(patch_datetime_now, schedule):
    response = _pypi_response(
        [
            {
                "filename": "demo_pkg-2.0.0-py3-none-any.whl",
                "upload-time": "2025-01-01T00:00:00Z",
            }
        ]
    )
    pyproject = _minimal_pyproject("Demo_Pkg>=1.0.0")
    pyproject["dependency-groups"] = {"dev": ["demo-pkg>=1.0.0"]}

    with patch.object(spec0_action.requests, "get", return_value=response) as get:
        update_pyproject_toml(pyproject, schedule, update_all=2.0)

    # Both spellings canonicalize to demo-pkg and share one PyPI request
    get.assert_called_once()
    assert get.call_args.args == ("https://pypi.org/simple/demo-pkg",)
    assert pyproject["project"]["dependencies"] == ["Demo_Pkg>=2.0.0"]
    assert pyproject["dependency-groups"]["dev"] == ["demo-pkg>=2.0.0"]


@pytest.mark.parametrize("update_all", [None, 2.0])
def test_excluded_pep_dependencies(patch_datetime_now, schedule, update_all):
    deps = [
        "NumPy[foo,bar] >= 1.10.0 ; python_version < '4'",
        "scikit_LEARN >= 1.0",
        "requests[socks] >= 2.0 ; sys_platform == 'win32'",
        "pandas>=1.0",
    ]
    pyproject = _minimal_pyproject(*deps)
    pyproject["project"]["optional-dependencies"] = {"test": deps.copy()}
    pyproject["dependency-groups"] = {"dev": deps.copy()}

    with _mock_pypi() as mock_pypi:
        update_pyproject_toml(
            pyproject,
            schedule,
            update_all,
            excluded_packages=["numpy", "NUMPY", "Scikit.Learn", "requests", "absent"],
        )

    mock_pypi.assert_not_called()
    expected = deps[:-1] + ["pandas>=2.2.0"]
    assert pyproject["project"]["dependencies"] == expected
    assert pyproject["project"]["optional-dependencies"]["test"] == expected
    assert pyproject["dependency-groups"]["dev"] == expected


@pytest.mark.parametrize(
    ("location", "table_name"),
    [
        ((), "dependencies"),
        (("feature", "test", "target", "linux-64"), "pypi-dependencies"),
    ],
)
def test_excluded_pixi_dependencies(patch_datetime_now, schedule, location, table_name):
    deps = {
        "NumPy": ">= 1.10.0",
        "scikit_learn": {"version": ">= 1.0", "extras": ["test"]},
        "pandas": {"version": ">=1.0", "extras": ["test"]},
    }
    expected = deepcopy(deps)
    expected["pandas"]["version"] = ">=2.2.0"
    pyproject = _minimal_pyproject()
    table = pyproject.setdefault("tool", {}).setdefault("pixi", {})
    for key in location:
        table = table.setdefault(key, {})
    table[table_name] = deps

    update_pyproject_toml(
        pyproject, schedule, excluded_packages=["numpy", "SCIKIT.LEARN"]
    )

    assert table[table_name] == expected


@pytest.mark.parametrize("current", [None, ">= 3.9, < 4"])
def test_excluded_python(patch_datetime_now, schedule, current):
    pixi = {"pixi": {"dependencies": {"Python": ">= 3.9"}}}
    pyproject = {"project": {"dependencies": ["numpy>=1.10.0"]}, "tool": deepcopy(pixi)}
    if current:
        pyproject["project"]["requires-python"] = current

    update_pyproject_toml(pyproject, schedule, excluded_packages=["PYTHON"])

    assert pyproject["project"].get("requires-python") == current
    assert pyproject["project"]["dependencies"] == ["numpy>=2.0.0"]
    assert pyproject["tool"] == pixi


def test_excluding_every_package_is_a_noop(patch_datetime_now, schedule):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    excluded = [pkg for entry in schedule for pkg in entry["packages"]]
    update_pyproject_toml(pyproject, schedule, excluded_packages=excluded)
    assert pyproject == _minimal_pyproject("numpy>=1.10.0")


@pytest.mark.parametrize("invalid", ["numpy>=1", "numpy[extra]"])
def test_invalid_exclusions_fail_before_mutation(patch_datetime_now, schedule, invalid):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    expected = deepcopy(pyproject)

    with _mock_pypi() as mock_pypi, pytest.raises(ValueError):
        update_pyproject_toml(
            pyproject, schedule, 2.0, excluded_packages=["pandas", invalid]
        )

    mock_pypi.assert_not_called()
    assert pyproject == expected


def test_exclusions_do_not_hide_invalid_schedule(patch_datetime_now):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    with pytest.raises(RuntimeError, match="Could not find schedule"):
        update_pyproject_toml(pyproject, [], excluded_packages=["numpy", "python"])
