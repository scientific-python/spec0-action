import datetime
import logging
from collections.abc import Callable, Sequence
from functools import cache
from itertools import pairwise

import requests
from packaging.requirements import Requirement
from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import Version

from spec0_action.parsing import (
    SupportSchedule,
    is_url_spec,
    parse_version_spec,
    read_schedule,
    read_toml,
    write_toml,
)
from spec0_action.versions import repr_spec_set, tighten_lower_bound

__all__ = [
    "CORE_PACKAGES",
    "read_schedule",
    "read_toml",
    "update_pyproject_toml",
    "write_toml",
]

CORE_PACKAGES = [
    "ipython",
    "matplotlib",
    "networkx",
    "numpy",
    "pandas",
    "scikit-image",
    "scikit-learn",
    "scipy",
    "xarray",
    "zarr",
]

logger = logging.getLogger(__name__)


@cache
def _get_release_dates(package: str) -> dict[Version, datetime.datetime]:
    """Fetch each stable version's earliest distribution upload from PyPI."""
    try:
        resp = requests.get(
            f"https://pypi.org/simple/{package}",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.warning("Could not fetch %s releases from PyPI: %s", package, exc)
        return {}
    first_uploads: dict[Version, datetime.datetime] = {}
    for f in data["files"]:
        ver = _version_from_filename(f["filename"])
        if ver is None or ver.is_prerelease:
            continue

        upload_time = datetime.datetime.fromisoformat(f["upload-time"])
        first_uploads[ver] = min(first_uploads.get(ver, upload_time), upload_time)
    return first_uploads


def _get_feature_release_dates(package: str) -> list[tuple[Version, datetime.datetime]]:
    """Return stable feature releases in version order, with their first uploads."""
    return sorted(
        (version, release_date)
        for version, release_date in _get_release_dates(package).items()
        if not version.is_postrelease and not any(version.release[2:])
    )


def _get_oldest_version_in_window(package: str, years: float) -> Version | None:
    """Return the oldest stable version first uploaded within ``years`` years."""
    cutoff = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(
        days=int(365 * years)
    )

    candidates = [
        ver
        for ver, first_upload in _get_release_dates(package).items()
        if first_upload >= cutoff
    ]
    return min(candidates, default=None)


def _get_spec0_floor(
    package: str, support_time: datetime.timedelta, now: datetime.datetime
) -> Version | None:
    """Advance to each successor at the quarter start of its predecessor's drop."""
    floor = None
    for (_, release_date), (successor, _) in pairwise(
        _get_feature_release_dates(package)
    ):
        if _quarter(release_date + support_time) <= _quarter(now):
            floor = successor
    return floor


def _quarter(date: datetime.datetime) -> tuple[int, int]:
    return date.year, (date.month - 1) // 3


def _version_from_filename(filename: str) -> Version | None:
    try:
        if filename.endswith(".whl"):
            return parse_wheel_filename(filename)[1]
        return parse_sdist_filename(filename)[1]
    except (InvalidWheelFilename, InvalidSdistFilename):
        return None


def update_pyproject_dependencies(
    dependencies: list,
    resolve_lower_bound: Callable[[str], Version | None],
    skip: set[str],
):
    # Assign by index so the (tomlkit) list is updated in place
    for i, dep_str in enumerate(dependencies):
        if not isinstance(dep_str, str):
            continue
        requirement = Requirement(dep_str)
        package_key = canonicalize_name(requirement.name)
        if requirement.url or package_key in skip:
            continue
        new_lower_bound = resolve_lower_bound(package_key)
        if new_lower_bound is None:
            continue
        new_spec = tighten_lower_bound(requirement.specifier, new_lower_bound)
        if new_spec is None or new_spec == requirement.specifier:
            # Skip no-op updates so unchanged specs keep their original formatting
            continue
        # Keep the original extras and marker spelling when rewriting the bound.
        suffix = dep_str.strip()[len(requirement.name) :].lstrip()
        extras = suffix[: suffix.index("]") + 1] if requirement.extras else ""
        _, separator, marker = dep_str.partition(";")
        dependencies[i] = (
            f"{requirement.name}{extras}{repr_spec_set(new_spec)}{separator}{marker}"
        )


def iter_pep_dependency_lists(pyproject_data: dict):
    project_data = pyproject_data.get("project")
    project_data = project_data if isinstance(project_data, dict) else {}
    groups = [project_data.get("dependencies")]
    for table in (
        project_data.get("optional-dependencies"),
        pyproject_data.get("dependency-groups"),
    ):
        if isinstance(table, dict):
            groups.extend(table.values())
    yield from (group for group in groups if isinstance(group, list))


def update_dependency_table(
    dep_table: dict,
    resolve_lower_bound: Callable[[str], Version | None],
    skip: set[str],
):
    for pkg, pkg_data in dep_table.items():
        package_key = canonicalize_name(pkg)
        if package_key in skip:
            continue
        # Like pkg = ">x.y.z,<a"
        if isinstance(pkg_data, str):
            if is_url_spec(pkg_data):
                continue
            spec_str = pkg_data
        elif isinstance(pkg_data, dict) and "version" in pkg_data:
            # Table like pkg = {version = ">x.y.z", ...}
            spec_str = pkg_data["version"]
        else:
            # We don't do anything with path, url, git, or other non-version dependencies
            continue
        try:
            current_spec = parse_version_spec(spec_str)
        except ValueError:
            # Conda-only expressions, such as version alternatives, stay unchanged.
            continue
        new_lower_bound = resolve_lower_bound(package_key)
        if new_lower_bound is None:
            continue
        new_spec = tighten_lower_bound(current_spec, new_lower_bound)
        if new_spec is None or new_spec == current_spec:
            continue
        if isinstance(pkg_data, str):
            dep_table[pkg] = repr_spec_set(new_spec)
        else:
            pkg_data["version"] = repr_spec_set(new_spec)


def update_pixi_dependencies(
    pixi_tables: dict,
    resolve_lower_bound: Callable[[str], Version | None],
    skip: set[str],
):
    for key in ("dependencies", "pypi-dependencies"):
        dep_table = pixi_tables.get(key)
        if isinstance(dep_table, dict):
            update_dependency_table(dep_table, resolve_lower_bound, skip)

    # Recurse into [tool.pixi.feature.X] and platform tables like
    # [tool.pixi.target.linux-64], which hold the same dependency keys
    for key in ("feature", "target"):
        subtables = pixi_tables.get(key)
        if isinstance(subtables, dict):
            for subtable in subtables.values():
                if isinstance(subtable, dict):
                    update_pixi_dependencies(subtable, resolve_lower_bound, skip)


def _update_requires_python(project_data: dict, new_lower_bound: Version):
    current_requires_python = project_data.get("requires-python")
    if not current_requires_python:
        project_data["requires-python"] = f">={new_lower_bound}"
        return
    try:
        current_spec = parse_version_spec(current_requires_python)
    except ValueError:
        # Leave specs we can't parse (e.g. poetry-style "^3.10") alone
        return
    new_spec = tighten_lower_bound(current_spec, new_lower_bound)
    if new_spec is not None and new_spec != current_spec:
        # Only write when the bound actually moved, to avoid cosmetic rewrites
        project_data["requires-python"] = repr_spec_set(new_spec)


def update_pyproject_toml(
    pyproject_data: dict,
    schedule_data: Sequence[SupportSchedule],
    update_all: float | None = None,
    *,
    excluded_packages: Sequence[str] = (),
    spec0_support_years: float | None = None,
):
    support_time = None
    if spec0_support_years is not None:
        try:
            support_time = datetime.timedelta(days=int(365 * spec0_support_years))
            if support_time < datetime.timedelta(days=1):
                raise ValueError
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                "spec0_support_years must be positive and at least one day"
            ) from exc
    now = datetime.datetime.now(datetime.UTC)
    applicable = sorted(
        filter(
            lambda s: now >= datetime.datetime.fromisoformat(s["start_date"]),
            schedule_data,
        ),
        key=lambda s: datetime.datetime.fromisoformat(s["start_date"]),
    )
    new_version: dict[str, Version] = {}
    for schedule in applicable:
        # Fill in the latest known requirement (schedule is sorted, newer entries overwrite older)
        for pkg, version in schedule["packages"].items():
            new_version[canonicalize_name(pkg)] = Version(version)
    if not new_version:
        raise RuntimeError(
            "Could not find schedule that applies to current time, perhaps your schedule is outdated."
        )
    project_data = pyproject_data.get("project", {})
    if not isinstance(project_data, dict):
        project_data = {}
    # Never touch excluded packages, nor self-references like "pkg[extras]" used
    # to share extras between dependency groups (their version is always the local one).
    skip = {canonicalize_name(pkg, validate=True) for pkg in excluded_packages}
    if "python" in new_version and "python" not in skip:
        _update_requires_python(project_data, new_version["python"])

    if isinstance(own_name := project_data.get("name"), str):
        skip.add(canonicalize_name(own_name))

    def resolve_lower_bound(
        package_key: str, *, use_update_all: bool = True
    ) -> Version | None:
        if support_time is not None and package_key in CORE_PACKAGES:
            return _get_spec0_floor(package_key, support_time, now)
        if package_key in new_version:
            return new_version[package_key]
        if use_update_all and update_all is not None:
            return _get_oldest_version_in_window(package_key, update_all)
        return None

    for dependencies in iter_pep_dependency_lists(pyproject_data):
        update_pyproject_dependencies(dependencies, resolve_lower_bound, skip)

    if "tool" in pyproject_data and "pixi" in pyproject_data["tool"]:
        update_pixi_dependencies(
            pyproject_data["tool"]["pixi"],
            lambda package: resolve_lower_bound(package, use_update_all=False),
            skip,
        )
