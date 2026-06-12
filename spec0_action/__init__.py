from functools import cache
from packaging.specifiers import SpecifierSet
from typing import Callable, Sequence, Dict
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


@cache
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
    first_uploads: dict[Version, datetime.datetime] = {}
    for f in data.get("files", []):
        ver = _version_from_filename(f.get("filename", ""))
        if ver is None or ver.is_prerelease:
            continue

        try:
            upload_time = datetime.datetime.fromisoformat(f.get("upload-time", ""))
        except ValueError:
            continue

        previous = first_uploads.get(ver)
        if previous is None or upload_time < previous:
            first_uploads[ver] = upload_time

    candidates = [
        ver for ver, first_upload in first_uploads.items() if first_upload >= cutoff
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
    dependencies: list,
    resolve_lower_bound: Callable[[str], Version | None],
    own_name: str | None,
):
    # Assign by index so the (tomlkit) list is updated in place
    for i, dep_str in enumerate(dependencies):
        if not isinstance(dep_str, str):
            continue
        pkg, extras, spec, env = parse_pep_dependency(dep_str)
        package_key = canonicalize_name(pkg)
        if isinstance(spec, Url) or package_key == own_name:
            continue
        new_lower_bound = resolve_lower_bound(package_key)
        if new_lower_bound is None:
            continue
        new_spec = tighten_lower_bound(spec or SpecifierSet(), new_lower_bound)
        if new_spec is None or new_spec == spec:
            # Skip no-op updates so unchanged specs keep their original formatting
            continue
        dependencies[i] = f"{pkg}{extras or ''}{repr_spec_set(new_spec)}{env or ''}"


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
    dep_table: dict, new_versions: Dict[str, Version], own_name: str | None
):
    for pkg, pkg_data in dep_table.items():
        package_key = canonicalize_name(pkg)
        if package_key == own_name or package_key not in new_versions:
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
        current_spec = parse_version_spec(spec_str)
        new_spec = tighten_lower_bound(current_spec, new_versions[package_key])
        if new_spec is None or new_spec == current_spec:
            continue
        if isinstance(pkg_data, str):
            dep_table[pkg] = repr_spec_set(new_spec)
        else:
            pkg_data["version"] = repr_spec_set(new_spec)


def update_pixi_dependencies(
    pixi_tables: dict, new_versions: Dict[str, Version], own_name: str | None
):
    for key in ("dependencies", "pypi-dependencies"):
        dep_table = pixi_tables.get(key)
        if isinstance(dep_table, dict):
            update_dependency_table(dep_table, new_versions, own_name)

    # Recurse into [tool.pixi.feature.X] and platform tables like
    # [tool.pixi.target.linux-64], which hold the same dependency keys
    for key in ("feature", "target"):
        subtables = pixi_tables.get(key)
        if isinstance(subtables, dict):
            for subtable in subtables.values():
                if isinstance(subtable, dict):
                    update_pixi_dependencies(subtable, new_versions, own_name)


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
):
    now = datetime.datetime.now(datetime.UTC)
    applicable = sorted(
        filter(
            lambda s: now >= datetime.datetime.fromisoformat(s["start_date"]),
            schedule_data,
        ),
        key=lambda s: datetime.datetime.fromisoformat(s["start_date"]),
    )
    new_version: Dict[str, Version] = {}
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
    # Self-references like "pkg[extras]" are used to share extras between
    # dependency groups, their version is always the local one so never pin it.
    own_name = project_data.get("name")
    own_name = canonicalize_name(own_name) if isinstance(own_name, str) else None

    if "python" in new_version:
        _update_requires_python(project_data, new_version["python"])

    def resolve_lower_bound(package_key: str) -> Version | None:
        if package_key in new_version:
            return new_version[package_key]
        if update_all is not None:
            return _get_oldest_version_in_window(package_key, update_all)
        return None

    for dependencies in iter_pep_dependency_lists(pyproject_data):
        update_pyproject_dependencies(dependencies, resolve_lower_bound, own_name)

    if "tool" in pyproject_data and "pixi" in pyproject_data["tool"]:
        update_pixi_dependencies(pyproject_data["tool"]["pixi"], new_version, own_name)
