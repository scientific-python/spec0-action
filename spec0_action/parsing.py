import json
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from tomlkit import dumps, loads


class SupportSchedule(TypedDict):
    start_date: str
    packages: dict[str, str]


def parse_version_spec(s: str) -> SpecifierSet:
    if s.strip() == "*":
        # Python version numeric components must be non-negative so this is okay
        # see https://packaging.python.org/en/latest/specifications/version-specifiers/
        return SpecifierSet(">=0")
    try:
        return SpecifierSet(s)
    except InvalidSpecifier:
        return SpecifierSet(f"=={s}" if "*" in s else f">={Version(s)}")


def write_toml(path: Path | str, data: dict):
    with open(path, "w") as file:
        contents = dumps(data)
        file.write(contents)


def read_toml(path: Path | str) -> dict:
    with open(path) as file:
        contents = file.read()
        return loads(contents)


def read_schedule(path: Path | str) -> Sequence[SupportSchedule]:
    with open(path) as file:
        return json.load(file)


def is_url_spec(str_spec: str | None) -> bool:
    if str_spec is None:
        return False

    return str_spec.strip().startswith("@")
