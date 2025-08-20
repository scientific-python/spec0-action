from typing import TypeAlias
from urllib.parse import ParseResult, urlparse
from tomlkit import dumps, loads
import json
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version
from typing import Dict, Sequence, Tuple, TypedDict
from pathlib import Path
from re import compile

# We won't actually do anything with URLs we just need to detect them
Url: TypeAlias = ParseResult

# Slightly modified version of https://packaging.python.org/en/latest/specifications/dependency-specifiers/#names
PEP_PACKAGE_IDENT_RE = compile(r"(?im)^([A-Z0-9][A-Z0-9._-]*)(\[[A-Z0-9._,-]+\])?(.*)$")


class SupportSchedule(TypedDict):
    start_date: str
    packages: Dict[str, str]


def parse_version_spec(s: str) -> SpecifierSet:
    if s.strip() == "*":
        # Python version numeric components must be non-negative so this is okay
        # see https://packaging.python.org/en/latest/specifications/version-specifiers/
        return SpecifierSet(">=0")
    try:
        # If we can simply parse it return it
        return SpecifierSet(s)
    except InvalidSpecifier:
        try:
            ver = Version(s)
        except InvalidVersion:
            raise ValueError(f"{s} is not a version or specifyer")

        return SpecifierSet(f">={ver}")


def write_toml(path: Path | str, data: dict):
    with open(path, "w") as file:
        contents = dumps(data)
        file.write(contents)


def read_toml(path: Path | str) -> dict:
    with open(path, "r") as file:
        contents = file.read()
        return loads(contents)


def read_schedule(path: Path | str) -> Sequence[SupportSchedule]:
    with open(path, "r") as file:
        return json.load(file)


def parse_pep_dependency(dep_str: str) -> Tuple[str, str | None, SpecifierSet | Url | None]:
    match = PEP_PACKAGE_IDENT_RE.match(dep_str)
    if match is None:
        raise ValueError("Could not find any valid python package identifier")

    pkg, extras, spec_str = match.groups()

    extras = extras or None

    if is_url_spec(spec_str):
        spec = urlparse(spec_str.split("@")[1])
    elif not spec_str:
        spec = None
    else:
        spec = SpecifierSet(spec_str)

    return (pkg, extras, spec)


def is_url_spec(str_spec: str|None) -> bool:
    if str_spec is None:
        return False

    return str_spec.strip().startswith("@")
