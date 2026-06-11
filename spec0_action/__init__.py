import contextlib
from collections import defaultdict
from packaging.specifiers import SpecifierSet
from typing import Sequence, Dict
import datetime
import requests

from spec0_action.versions import repr_spec_set, tighten_lower_bound
from spec0_action.parsing import (
    SupportSchedule,
    Url,
    is_url_spec,
    parse_pep_dependency,
    parse_version_spec,
    read_schedule,
    read_toml,
    write_toml,
)
from packaging.version import Version
from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)

__all__ = ["read_schedule", "read_toml", "write_toml", "update_pyproject_toml"]


def _get_oldest_version_in_window(package: str, years: float) -> Version | None:
    """
    Query PyPI, return oldest non-pre release version uploaded within the last ``years`` years.
    """
    cutoff = datetime.datetime.now(tz=datetime.timezone.utc) - datetime.timedelta(
        days=int(365 * years)
    )
    try:
        resp = requests.get(
            f"https://pypi.org/simple/{package}",
            headers={"Accept": "application/vnd.pypi.simple.v1+json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None
    release_dates: dict[Version, list[datetime.datetime]] = defaultdict(list)
    for f in data.get("files", []):
        ver = _version_from_filename(f.get("filename", ""))
        if ver is None or ver.is_prerelease:
            continue

        upload_str = f.get("upload-time", "")
        upload_time = None
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]:
            with contextlib.suppress(ValueError):
                upload_time = datetime.datetime.strptime(upload_str, fmt).replace(
                    tzinfo=datetime.timezone.utc
                )
                break
        if upload_time is None:
            continue
        release_dates[ver].append(upload_time)

    candidates = [
        ver
        for ver, upload_times in release_dates.items()
        if min(upload_times) >= cutoff
    ]
    return min(candidates, default=None)


def _version_from_filename(filename: str) -> Version | None:
    try:
        _, version, _, _ = parse_wheel_filename(filename)
        return version
    except InvalidWheelFilename:
        pass

    try:
        _, version = parse_sdist_filename(filename)
        return version
    except InvalidSdistFilename:
        return None


def update_pyproject_dependencies(
    dependencies: list, schedule: Dict[str, str], own_name: str | None = None
):
    # Iterate by idx because we want to update it inplace
    for i in range(len(dependencies)):
        dep_str = dependencies[i]
        if not isinstance(dep_str, str):
            continue
        pkg, extras, spec, env = parse_pep_dependency(dep_str)
        schedule_key = canonicalize_name(pkg)
        if (
            isinstance(spec, Url)
            or schedule_key == own_name
            or schedule_key not in schedule
        ):
            continue
        new_lower_bound = Version(schedule[schedule_key])
        try:
            spec = tighten_lower_bound(spec or SpecifierSet(), new_lower_bound)
            # Will raise a value error if bound is already tighter, in this case we just do nothing and  continue
        except ValueError:
            continue
        if not extras:
            new_dep_str = f"{pkg}{repr_spec_set(spec)}{env or ''}"
        else:
            new_dep_str = f"{pkg}{extras}{repr_spec_set(spec)}{env or ''}"
        dependencies[i] = new_dep_str


def iter_pep_dependency_lists(pyproject_data: dict, project_data: dict):
    dependencies = project_data.get("dependencies")
    if isinstance(dependencies, list):
        yield dependencies

    optional_dependencies = project_data.get("optional-dependencies", {})
    if isinstance(optional_dependencies, dict):
        for dependencies in optional_dependencies.values():
            if isinstance(dependencies, list):
                yield dependencies

    dependency_groups = pyproject_data.get("dependency-groups", {})
    if isinstance(dependency_groups, dict):
        for dependencies in dependency_groups.values():
            if isinstance(dependencies, list):
                yield dependencies


def update_dependency_table(
    dep_table: dict, new_versions: dict, own_name: str | None = None
):
    for pkg, pkg_data in dep_table.items():
        schedule_key = canonicalize_name(pkg)
        # Don't do anything for the package itself or pkgs that aren't in our schedule
        if schedule_key == own_name or schedule_key not in new_versions:
            continue
        # Like pkg = ">x.y.z,<a"
        if isinstance(pkg_data, str):
            if not is_url_spec(pkg_data):
                spec = parse_version_spec(pkg_data)
                new_lower_bound = Version(new_versions[schedule_key])
                try:
                    spec = tighten_lower_bound(spec, new_lower_bound)
                except ValueError:
                    continue
                dep_table[pkg] = repr_spec_set(spec)
            else:
                # We don't do anything with url spec dependencies
                continue
        else:
            # Table like in tests = {path = "."}
            if not isinstance(pkg_data, dict) or "version" not in pkg_data:
                # We don't do anything with path, url, git, or other non-version dependencies
                continue
            spec = parse_version_spec(pkg_data["version"])
            new_lower_bound = Version(new_versions[schedule_key])
            try:
                spec = tighten_lower_bound(spec, new_lower_bound)
            except ValueError:
                continue
            pkg_data["version"] = repr_spec_set(spec)


def update_pixi_dependencies(
    pixi_tables: dict, schedule: Dict[str, str], own_name: str | None = None
):
    if "pypi-dependencies" in pixi_tables:
        update_dependency_table(pixi_tables["pypi-dependencies"], schedule, own_name)
    if "dependencies" in pixi_tables:
        update_dependency_table(pixi_tables["dependencies"], schedule, own_name)

    if "feature" in pixi_tables:
        for _, feature_data in pixi_tables["feature"].items():
            if "dependencies" in feature_data:
                update_dependency_table(
                    feature_data["dependencies"], schedule, own_name
                )
            if "pypi-dependencies" in feature_data:
                update_dependency_table(
                    feature_data["pypi-dependencies"], schedule, own_name
                )


def update_pyproject_toml(
    pyproject_data: dict,
    schedule_data: Sequence[SupportSchedule],
    update_all: float | None = None,
):
    now = datetime.datetime.now(datetime.UTC)
    applicable = sorted(
        filter(
            lambda s: now >= datetime.datetime.fromisoformat(s["start_date"]),
            schedule_data,
        ),
        key=lambda s: datetime.datetime.fromisoformat(s["start_date"]),
    )
    new_version = {}
    for schedule in applicable:
        # Fill in the latest known requirement (schedule is sorted, newer entries overwrite older)
        for pkg, version in schedule["packages"].items():
            new_version[canonicalize_name(pkg)] = version
    if not new_version:
        raise RuntimeError(
            "Could not find schedule that applies to current time, perhaps your schedule is outdated."
        )
    project_data = pyproject_data.get("project", {})
    if not isinstance(project_data, dict):
        project_data = {}
    # Self-references like "pkg[extras]" are used to share extras between
    # dependency groups, their version is always the local one so never pin it.
    own_name = project_data.get("name")
    if isinstance(own_name, str):
        own_name = canonicalize_name(own_name)
    else:
        own_name = None
    if "python" in new_version and isinstance(project_data, dict):
        current_requires_python = project_data.get("requires-python")
        if current_requires_python:
            try:
                python_spec = tighten_lower_bound(
                    parse_version_spec(current_requires_python),
                    Version(new_version["python"]),
                )
            except ValueError:
                python_spec = parse_version_spec(current_requires_python)
        else:
            python_spec = parse_version_spec(new_version["python"])
        project_data["requires-python"] = repr_spec_set(python_spec)

    for dependencies in iter_pep_dependency_lists(pyproject_data, project_data):
        update_pyproject_dependencies(dependencies, new_version, own_name)

    if "tool" in pyproject_data and "pixi" in pyproject_data["tool"]:
        pixi_data = pyproject_data["tool"]["pixi"]
        update_pixi_dependencies(pixi_data, new_version, own_name)
    if update_all is not None:
        for deps in iter_pep_dependency_lists(pyproject_data, project_data):
            for i, dep_str in enumerate(deps):
                if not isinstance(dep_str, str):
                    continue
                pkg, extras, spec, env = parse_pep_dependency(dep_str)
                if (
                    canonicalize_name(pkg) in new_version
                    or canonicalize_name(pkg) == own_name
                    or isinstance(spec, Url)
                ):
                    continue
                min_ver = _get_oldest_version_in_window(pkg, update_all)
                if min_ver is None:
                    continue
                try:
                    updated = tighten_lower_bound(spec or SpecifierSet(), min_ver)
                    deps[i] = f"{pkg}{extras or ''}{repr_spec_set(updated)}{env or ''}"
                except ValueError:
                    continue
