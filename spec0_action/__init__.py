from packaging.specifiers import SpecifierSet
from typing import Sequence, cast
import datetime

from spec0_action.versions import repr_spec_set, tighten_lower_bound
from spec0_action.parsing import (
    SupportSchedule,
    Url,
    is_url_spec,
    parse_pep_dependency,
    parse_version_spec,
    read_schedule,
    read_toml,
    write_toml
)
from packaging.version import Version


__all__ = ["read_schedule", "read_toml", "write_toml", "update_pyproject_toml"]

def update_pyproject_dependencies(dependencies: dict, schedule: SupportSchedule):
    # iterate by idx because we want to update it inplace
    for i in range(len(dependencies)):
        dep_str = dependencies[i]
        pkg, extras, spec = parse_pep_dependency(dep_str)

        if isinstance(spec, Url) or pkg not in schedule["packages"]:
            continue

        new_lower_bound = Version(schedule["packages"][pkg])
        try:
            spec = tighten_lower_bound(spec or SpecifierSet(), new_lower_bound)
            # will raise a value error if bound is already tigheter, in this case we just do nothing and  continue


        except ValueError:
            continue

        if not extras:
            new_dep_str = f"{pkg}{repr_spec_set(spec)}"
        else:
            new_dep_str = f"{pkg}{extras}{repr_spec_set(spec)}"

        dependencies[i] = new_dep_str


def update_dependency_table(dep_table: dict, new_versions: dict):
    for pkg, pkg_data in dep_table.items():
        # don't do anything for pkgs that aren't in our schedule
        if pkg not in new_versions:
            continue

        # like pkg = ">x.y.z,<a"
        if isinstance(pkg_data, str):
            if not is_url_spec(pkg_data):
                spec = parse_version_spec(pkg_data)

                new_lower_bound = Version(new_versions[pkg])
                spec = tighten_lower_bound(spec, new_lower_bound)

                dep_table[pkg] = repr_spec_set(spec)

            else:
                # we don't do anything with url spec dependencies
                continue
        else:
            # table like in tests = {path = "."}
            if "path" in pkg_data:
                # we don't do anything with path dependencies
                continue

            spec = SpecifierSet(pkg_data["version"])
            new_lower_bound = Version(new_versions[pkg])
            spec = tighten_lower_bound(spec, new_lower_bound)

            pkg_data["version"] = repr_spec_set(spec)


def update_pixi_dependencies(pixi_tables: dict, schedule: SupportSchedule):
    if "pypi-dependencies" in pixi_tables: 
        update_dependency_table(pixi_tables["pypi-dependencies"], schedule["packages"])
    if "dependencies" in pixi_tables: 
        update_dependency_table(pixi_tables["dependencies"], schedule["packages"])

    if "feature" in pixi_tables:
        for _, feature_data in pixi_tables["feature"].items():
            if "dependencies" in feature_data:
                update_dependency_table(feature_data["dependencies"], schedule["packages"])


def update_pyproject_toml(
    pyproject_data: dict, schedule_data: Sequence[SupportSchedule]
):
    now = datetime.datetime.now(datetime.UTC)
    try:
        new_version = cast(
            SupportSchedule,
            next(
                filter(
                    lambda s: now >= datetime.datetime.fromisoformat(s["start_date"]),
                    schedule_data,
                )
            ),
        )
    except StopIteration:
        raise RuntimeError(
            "Could not find schedule that applies to current time, perhaps your schedule is oudated."
        )

    if "python" in new_version["packages"]:
        pyproject_data["project"]["requires-python"] = repr_spec_set(
            parse_version_spec(new_version["packages"]["python"])
        )

    update_pyproject_dependencies(
        pyproject_data["project"]["dependencies"], new_version
    )

    if "tool" in pyproject_data and "pixi" in pyproject_data['tool']:
        pixi_data = pyproject_data["tool"]["pixi"]
        update_pixi_dependencies(pixi_data, new_version)
