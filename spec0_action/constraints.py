"""Exact SPEC 0 minimum version pins for testing the oldest supported versions in CI."""

import datetime
from collections.abc import Iterable, Sequence

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from spec0_action.parsing import SupportSchedule


class ScheduleError(ValueError):
    """The schedule is malformed or cannot provide a requested floor."""


def _parse_start_date(entry: SupportSchedule, index: int) -> datetime.datetime:
    try:
        start = datetime.datetime.fromisoformat(entry["start_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ScheduleError(
            f"schedule entry {index} has a missing or invalid start_date"
        ) from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=datetime.UTC)
    return start


def schedule_floors(
    schedule_data: Sequence[SupportSchedule], reference_date: datetime.datetime
) -> dict[str, Version]:
    """Return the minimum version of every package in the schedule on ``reference_date``.

    Each schedule entry only lists the packages whose floor changes at its start date,
    so all entries up to the reference date are applied in order and later entries
    overwrite earlier ones.
    """
    if reference_date.tzinfo is None:
        reference_date = reference_date.replace(tzinfo=datetime.UTC)
    if not isinstance(schedule_data, Sequence) or isinstance(schedule_data, str):
        raise ScheduleError("the schedule must be a list of entries")

    dated = []
    for index, entry in enumerate(schedule_data):
        if not isinstance(entry, dict) or not isinstance(entry.get("packages"), dict):
            raise ScheduleError(f"schedule entry {index} has no packages mapping")
        dated.append((_parse_start_date(entry, index), index, entry))

    floors: dict[str, Version] = {}
    for start, index, entry in sorted(dated, key=lambda item: item[0]):
        if start > reference_date:
            break
        for package, version in entry["packages"].items():
            try:
                floors[canonicalize_name(package)] = Version(version)
            except (InvalidVersion, TypeError) as exc:
                raise ScheduleError(
                    f"schedule entry {index} has an invalid version {version!r} for {package}"
                ) from exc
    return floors


def parse_package_list(packages: str | Iterable[str]) -> list[str]:
    """Split a comma- or whitespace-separated list and normalize the names, keeping order."""
    if isinstance(packages, str):
        packages = packages.replace(",", " ").split()
    names: list[str] = []
    for package in packages:
        name = canonicalize_name(package, validate=True)
        if name not in names:
            names.append(name)
    return names


def minimum_versions(
    schedule_data: Sequence[SupportSchedule],
    packages: str | Iterable[str],
    reference_date: datetime.datetime,
) -> dict[str, Version]:
    """Return the SPEC 0 floor of each requested package, failing if any is unknown."""
    requested = parse_package_list(packages)
    if not requested:
        raise ScheduleError("no packages were requested")
    floors = schedule_floors(schedule_data, reference_date)
    missing = [package for package in requested if package not in floors]
    if missing:
        raise ScheduleError(
            f"the schedule has no floor on {reference_date.date()} for: {', '.join(missing)}"
        )
    return {package: floors[package] for package in requested}


def format_constraints(versions: dict[str, Version]) -> str:
    """Format exact pins for a pip/uv constraints file.

    Exact pins are needed: with ``>=`` the installer would pick the newest release and
    the oldest supported version would never be tested. Python is not a package, so it
    is left out here and reported separately.
    """
    lines = [
        f"{package}=={version}"
        for package, version in versions.items()
        if package != "python"
    ]
    return "".join(f"{line}\n" for line in lines)
