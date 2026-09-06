import pytest
from packaging.specifiers import SpecifierSet

from spec0_action.parsing import parse_version_spec


@pytest.mark.parametrize(
    ("spec_str", "expected"),
    [
        ("*", SpecifierSet(">=0")),
        (">4, <9", SpecifierSet(">4,<9")),
        (">=4", SpecifierSet(">=4")),
        ("1.2.3", SpecifierSet(">=1.2.3")),
        ("3.11.*", SpecifierSet("==3.11.*")),
    ],
)
def test_parse_version_spec(spec_str, expected):
    assert parse_version_spec(spec_str) == expected


@pytest.mark.parametrize("spec_str", ["-18", "asdf"])
def test_parse_version_spec_invalid(spec_str):
    with pytest.raises(ValueError):
        parse_version_spec(spec_str)
