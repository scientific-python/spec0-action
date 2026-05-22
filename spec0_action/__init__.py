import contextlib
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
from packaging.version import Version, InvalidVersion

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
    candidates: list[Version] = []
    for f in data.get("files", []):
        parts = f.get("filename", "").split("-")
        if len(parts) < 2:
            continue
        try:
            ver = Version(parts[1])
        except InvalidVersion:
            continue
        if ver.is_prerelease:
            continue
        upload_str = f.get("upload-time", "")
        upload_time = None
        for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]:
            with contextlib.suppress(ValueError):
                upload_time = datetime.datetime.strptime(upload_str, fmt).replace(
                    tzinfo=datetime.timezone.utc
                )
                break
        if upload_time is None or upload_time < cutoff:
            continue
        candidates.append(ver)

    return min(candidates, default=None)


def update_pyproject_dependencies(dependencies: dict, schedule: Dict[str, str]):
    # Iterate by idx because we want to update it inplace
    for i in range(len(dependencies)):
        dep_str = dependencies[i]
        pkg, extras, spec, env = parse_pep_dependency(dep_str)
        if isinstance(spec, Url) or pkg not in schedule:
            continue
        new_lower_bound = Version(schedule[pkg])
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


def update_dependency_table(dep_table: dict, new_versions: dict):
    for pkg, pkg_data in dep_table.items():
        # Don't do anything for pkgs that aren't in our schedule
        if pkg not in new_versions:
            continue
        # Like pkg = ">x.y.z,<a"
        if isinstance(pkg_data, str):
            if not is_url_spec(pkg_data):
                spec = parse_version_spec(pkg_data)
                new_lower_bound = Version(new_versions[pkg])
                spec = tighten_lower_bound(spec, new_lower_bound)
                dep_table[pkg] = repr_spec_set(spec)
            else:
                # We don't do anything with url spec dependencies
                continue
        else:
            # Table like in tests = {path = "."}
            if "path" in pkg_data:
                # We don't do anything with path dependencies
                continue
            spec = SpecifierSet(pkg_data["version"])
            new_lower_bound = Version(new_versions[pkg])
            spec = tighten_lower_bound(spec, new_lower_bound)
            pkg_data["version"] = repr_spec_set(spec)


def update_pixi_dependencies(pixi_tables: dict, schedule: Dict[str, str]):
    if "pypi-dependencies" in pixi_tables:
        update_dependency_table(pixi_tables["pypi-dependencies"], schedule)
    if "dependencies" in pixi_tables:
        update_dependency_table(pixi_tables["dependencies"], schedule)

    if "feature" in pixi_tables:
        for _, feature_data in pixi_tables["feature"].items():
            if "dependencies" in feature_data:
                update_dependency_table(feature_data["dependencies"], schedule)


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
            new_version[pkg] = version
    if not new_version:
        raise RuntimeError(
            "Could not find schedule that applies to current time, perhaps your schedule is outdated."
        )
    if "python" in new_version:
        pyproject_data["project"]["requires-python"] = repr_spec_set(
            parse_version_spec(new_version["python"])
        )
    update_pyproject_dependencies(
        pyproject_data["project"]["dependencies"], new_version
    )
    if "tool" in pyproject_data and "pixi" in pyproject_data["tool"]:
        pixi_data = pyproject_data["tool"]["pixi"]
        update_pixi_dependencies(pixi_data, new_version)
    if update_all is not None:
        deps = pyproject_data.get("project", {}).get("dependencies", [])
        for i, dep_str in enumerate(deps):
            pkg, extras, spec, env = parse_pep_dependency(dep_str)
            if pkg in new_version or isinstance(spec, Url) or spec is None:
                continue
            min_ver = _get_oldest_version_in_window(pkg, update_all)
            if min_ver is None:
                continue
            try:
                updated = tighten_lower_bound(spec, min_ver)
                deps[i] = f"{pkg}{extras or ''}{repr_spec_set(updated)}{env or ''}"
            except ValueError:
                continue
