from spec0_action.parsing import parse_version_spec, parse_pep_dependency
from packaging.specifiers import SpecifierSet
import pytest
from urllib.parse import urlparse

URL = "https://github.com/pypa/pip/archive/1.3.1.zip#sha1=da9234ee9982d4bbb3c72346a6de940a148ea686"


@pytest.mark.parametrize(
    ("spec_str", "expected"),
    [
        ("*", SpecifierSet(">=0")),
        (">4, <9", SpecifierSet(">4,<9")),
        (">=4", SpecifierSet(">=4")),
        (">=2025.7", SpecifierSet(">=2025.7")),
        ("3.11.*", SpecifierSet("==3.11.*")),
    ],
)
def test_parse_version_spec(spec_str, expected):
    assert parse_version_spec(spec_str) == expected


@pytest.mark.parametrize("spec_str", ["-18", "asdf"])
def test_parse_version_spec_invalid(spec_str):
    with pytest.raises(ValueError):
        parse_version_spec(spec_str)


@pytest.mark.parametrize(
    ("dep_str", "expected"),
    [
        ("matplotlib", ("matplotlib", None, None, None)),
        ("ruamel.yaml", ("ruamel.yaml", None, None, None)),
        (
            "matplotlib>=3.7.0,<4",
            ("matplotlib", None, SpecifierSet(">=3.7.0,<4"), None),
        ),
        ("matplotlib >= 3.7.0", ("matplotlib", None, SpecifierSet(">=3.7.0"), None)),
        (
            "matplotlib[foo,bar]>=3.7.0,<4",
            ("matplotlib", "[foo,bar]", SpecifierSet(">=3.7.0,<4"), None),
        ),
        (
            "matplotlib>=3.7.0,<4,!=3.8.14",
            ("matplotlib", None, SpecifierSet("!=3.8.14,<4,>=3.7.0"), None),
        ),
        (
            "matplotlib>=3.7.0,<4;sys_platform != 'win32'",
            (
                "matplotlib",
                None,
                SpecifierSet(">=3.7.0,<4"),
                ";sys_platform != 'win32'",
            ),
        ),
        (f"matplotlib @ {URL}", ("matplotlib", None, urlparse(f" {URL}"), None)),
    ],
)
def test_parse_pep_dependency(dep_str, expected):
    assert parse_pep_dependency(dep_str) == expected
