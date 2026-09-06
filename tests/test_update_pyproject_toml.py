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
    spec0_action._get_release_dates.cache_clear()


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
    with patch.object(spec0_action.requests, "get") as get:
        update_pyproject_toml(pyproject, schedule)
    get.assert_not_called()
    assert pyproject == read_toml(f"tests/test_data/{name}_updated.toml")


@pytest.mark.parametrize(
    ("dependency", "expected"),
    [
        ("xarray[io]>=2026.5.1", "xarray[io]>=2026.7.0"),
        (
            " xarray [io, parallel] (>=2026.5.1) ; python_version < '4'",
            "xarray[io, parallel]>=2026.7.0; python_version < '4'",
        ),
        ("xarray[io] >= 2026.8.0", "xarray[io] >= 2026.8.0"),
    ],
)
def test_pep_requirement_extras_and_whitespace(
    patch_datetime_now, dependency, expected
):
    pyproject = _minimal_pyproject(dependency)
    schedule = [
        {"start_date": "2000-01-01T00:00:00Z", "packages": {"xarray": "2026.7.0"}}
    ]
    update_pyproject_toml(pyproject, schedule)
    assert pyproject["project"]["dependencies"] == [expected]


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
                "numpy": ">=1.26|>=2.0",
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
    assert pixi["dependencies"]["numpy"] == ">=1.26|>=2.0"
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
@pytest.mark.parametrize("spec0_support_years", [None, 3])
def test_update_all_preserves_dependency_on_pypi_failure(
    patch_datetime_now, schedule, stage, error, spec0_support_years, caplog
):
    package = "numpy" if spec0_support_years else "requests"
    dependency = f"{package} >= 1.0"
    pyproject = _minimal_pyproject(dependency)
    pyproject["tool"] = {"pixi": {"dependencies": {package: ">= 1.0"}}}
    with patch.object(spec0_action.requests, "get") as get:
        operation = get if stage == "get" else getattr(get.return_value, stage)
        operation.side_effect = error
        update_pyproject_toml(
            pyproject, schedule, update_all=2.0, spec0_support_years=spec0_support_years
        )

    assert pyproject["project"]["dependencies"] == [dependency]
    assert pyproject["tool"]["pixi"]["dependencies"] == {package: ">= 1.0"}
    get.assert_called_once()
    assert f"Could not fetch {package} releases" in caplog.text


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


@pytest.mark.parametrize("spec0_support_years", [None, 3])
def test_excluding_every_package_is_a_noop(
    patch_datetime_now, schedule, spec0_support_years
):
    pyproject = _minimal_pyproject("numpy>=1.10.0")
    excluded = [pkg for entry in schedule for pkg in entry["packages"]]
    with patch.object(spec0_action.requests, "get") as get:
        update_pyproject_toml(
            pyproject,
            schedule,
            excluded_packages=excluded,
            spec0_support_years=spec0_support_years,
        )
    assert pyproject == _minimal_pyproject("numpy>=1.10.0")
    get.assert_not_called()


def test_update_all_includes_unscheduled_core_packages(patch_datetime_now):
    pyproject = _minimal_pyproject("numpy>=1.0")
    schedule = [{"start_date": "2025-10-01T00:00:00Z", "packages": {"python": "3.12"}}]
    with _mock_pypi("1.26") as fallback:
        update_pyproject_toml(pyproject, schedule, update_all=3)
    assert pyproject["project"]["dependencies"] == ["numpy>=1.26"]
    fallback.assert_called_once_with("numpy", 3)


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


@pytest.fixture
def feature_files():
    # Full history, a source-only release, duplicate distributions, and an old
    # feature's late wheel. Non-feature versions must never advance the floor.
    return [
        {"filename": filename, "upload-time": date}
        for filename, date in [
            ("example-1.4.0.tar.gz", "2025-09-01T00:00:00Z"),
            ("example-1.3.0.tar.gz", "2024-11-25T00:00:00Z"),
            ("example-1.2.0.tar.gz", "2023-11-25T00:00:00Z"),
            ("example-1.1.0-py3-none-any.whl", "2025-01-01T00:00:00Z"),
            ("example-1.1.0.tar.gz", "2022-11-25T00:00:00.000Z"),
            ("example-1.1.0.zip", "2022-11-26T00:00:00Z"),
            ("example-1.0.0.tar.gz", "2019-12-31T00:00:00Z"),
            ("example-1.3.0rc1.tar.gz", "2020-01-01T00:00:00Z"),
            ("example-1.3.0.dev1.tar.gz", "2020-01-01T00:00:00Z"),
            ("example-1.3.0.post1.tar.gz", "2020-01-01T00:00:00Z"),
            ("example-1.3.1.tar.gz", "2020-01-01T00:00:00Z"),
            ("example-1.3.0.1.tar.gz", "2020-01-01T00:00:00Z"),
            ("example-1.3.0-py2.7.egg", "2020-01-01T00:00:00Z"),
        ]
    ]


@pytest.mark.parametrize(
    ("years", "expected"),
    [(1, "1.4.0"), (2, "1.3.0"), (3, "1.2.0"), (5, "1.1.0"), (8, "1.0")],
)
def test_custom_support_period(
    patch_datetime_now, schedule, feature_files, years, expected
):
    pyproject = _minimal_pyproject("numpy>=1.0")
    with patch.object(
        spec0_action.requests, "get", return_value=_pypi_response(feature_files)
    ) as get:
        update_pyproject_toml(pyproject, schedule, spec0_support_years=years)
    assert pyproject["project"]["dependencies"] == [f"numpy>={expected}"]
    assert pyproject["project"]["requires-python"] == ">=3.12"
    get.assert_called_once_with(
        "https://pypi.org/simple/numpy",
        headers={"Accept": "application/vnd.pypi.simple.v1+json"},
        timeout=15,
    )


@pytest.mark.parametrize(
    ("release_date", "years", "now", "expected"),
    [
        ("2024-12-31T12:00:00Z", 1, "2025-09-30T23:59:59Z", "numpy >= 1.0"),
        ("2024-12-31T12:00:00Z", 1, "2025-10-01T00:00:00Z", "numpy>=1.1"),
        # Crossing leap day makes the anniversary March 31, so the drop is Q1.
        ("2023-04-01T00:00:00Z", 1, "2023-12-31T23:59:59Z", "numpy >= 1.0"),
        ("2023-04-01T00:00:00Z", 1, "2024-01-01T00:00:00Z", "numpy>=1.1"),
        ("2025-09-30T00:00:00Z", 1 / 365, "2025-10-01T00:00:00Z", "numpy>=1.1"),
    ],
)
def test_custom_support_quarter_boundaries(
    patch_datetime_now, monkeypatch, release_date, years, now, expected
):
    monkeypatch.setattr(f"{__name__}.FAKE_TIME", datetime.datetime.fromisoformat(now))
    pyproject = _minimal_pyproject("numpy >= 1.0")
    schedule = [{"start_date": "2000-01-01T00:00:00Z", "packages": {"python": "3.12"}}]
    files = [
        {"filename": f"numpy-{version}.tar.gz", "upload-time": release_date}
        for version in ("1.0", "1.1")
    ]
    with patch.object(spec0_action.requests, "get", return_value=_pypi_response(files)):
        update_pyproject_toml(pyproject, schedule, spec0_support_years=years)
    assert pyproject["project"]["dependencies"] == [expected]


def test_custom_support_covers_pep_and_pixi_without_core_schedule_entries(
    patch_datetime_now, feature_files
):
    # A custom schedule still owns Python and additional packages; membership
    # in the core policy cannot depend on entries in this schedule.
    schedule = [
        {
            "start_date": "2025-10-01T00:00:00Z",
            "packages": {"python": "3.12", "custom-pkg": "4.0"},
        }
    ]
    pyproject = _minimal_pyproject(
        "SCIKIT_LEARN[extra]>=1.0;python_version<'4'", "requests>=1", "custom-pkg>=1"
    )
    pixi = {
        "dependencies": {
            "SCIKIT_LEARN": ">=1.0",
            "requests": ">=1",
            "custom-pkg": ">=1",
            "python": ">=3.9",
        },
    }
    target = {
        "pypi-dependencies": {"scikit-learn": {"version": ">=1.0", "extras": ["test"]}}
    }
    pixi["feature"] = {"test": {"target": {"linux-64": target}}}
    pyproject["tool"] = {"pixi": pixi}

    with patch.object(
        spec0_action.requests, "get", return_value=_pypi_response(feature_files)
    ) as get:
        update_pyproject_toml(pyproject, schedule, update_all=2, spec0_support_years=3)

    assert pyproject["project"]["dependencies"] == [
        "SCIKIT_LEARN[extra]>=1.2.0;python_version<'4'",
        "requests>=1.2.0",  # Existing update_all policy selects oldest in window.
        "custom-pkg>=4.0",
    ]
    assert pyproject["project"]["requires-python"] == ">=3.12"
    assert pixi["dependencies"] == {
        "SCIKIT_LEARN": ">=1.2.0",
        "requests": ">=1",
        "custom-pkg": ">=4.0",
        "python": ">=3.12",
    }
    assert target["pypi-dependencies"] == {
        "scikit-learn": {"version": ">=1.2.0", "extras": ["test"]}
    }
    assert [c.args[0] for c in get.call_args_list] == [
        "https://pypi.org/simple/scikit-learn",
        "https://pypi.org/simple/requests",
    ]


def test_custom_support_skips_excluded_and_non_version_dependencies(
    patch_datetime_now, schedule
):
    pyproject = _minimal_pyproject(
        "scipy @ https://example.invalid/scipy.whl",
        "scikit_LEARN[tests]",
        "pandas >= 1",
        "requests >= 1",
    )
    pyproject["project"]["name"] = "scikit-learn"
    pixi = {
        "dependencies": {"pandas": ">= 1", "python": ">= 3.9"},
        "pypi-dependencies": {
            "scipy": "@ https://example.invalid/scipy.whl",
            "scikit-learn": {"version": "*", "extras": ["tests"]},
            "xarray": {"git": "https://example.invalid/xarray.git"},
        },
    }
    pyproject["tool"] = {"pixi": pixi}
    expected = deepcopy(pyproject)
    with patch.object(spec0_action.requests, "get") as get:
        update_pyproject_toml(
            pyproject,
            schedule,
            update_all=2,
            spec0_support_years=3,
            excluded_packages=["Pandas", "requests", "PYTHON"],
        )
    assert pyproject == expected
    get.assert_not_called()


@pytest.mark.parametrize(
    "files",
    [
        [],
        [
            {
                "filename": "numpy-1.0.post1.tar.gz",
                "upload-time": "2020-01-01T00:00:00Z",
            }
        ],
        [{"filename": "numpy-1.0.tar.gz", "upload-time": "2000-01-01T00:00:00Z"}],
    ],
)
def test_custom_support_without_a_floor_never_falls_back(
    patch_datetime_now, schedule, files
):
    pyproject = _minimal_pyproject("numpy >= 0.5")
    pyproject["tool"] = {"pixi": {"dependencies": {"numpy": ">= 0.5"}}}
    with (
        patch.object(
            spec0_action.requests,
            "get",
            return_value=_pypi_response(files),
        ) as get,
        _mock_pypi() as fallback,
    ):
        update_pyproject_toml(pyproject, schedule, update_all=2, spec0_support_years=3)
    assert pyproject["project"]["dependencies"] == ["numpy >= 0.5"]
    assert pyproject["tool"]["pixi"]["dependencies"] == {"numpy": ">= 0.5"}
    get.assert_called_once()
    fallback.assert_not_called()


@pytest.mark.parametrize("years", [0, -1, float("nan"), float("inf"), 3_000_000])
def test_invalid_support_period_fails_before_mutation(
    patch_datetime_now, schedule, years
):
    pyproject = _minimal_pyproject("numpy>=1")
    expected = deepcopy(pyproject)
    with (
        patch.object(spec0_action.requests, "get") as get,
        pytest.raises(ValueError, match="spec0_support_years"),
    ):
        update_pyproject_toml(pyproject, schedule, spec0_support_years=years)
    assert pyproject == expected
    get.assert_not_called()
