from packaging.version import Version
from spec0_action.versions import repr_spec_set, tighten_lower_bound
from packaging.specifiers import SpecifierSet
import pytest


def test_repr_specset():
    spec = SpecifierSet("<7,!=3.8.0,>4,~=3.14")
    assert repr_spec_set(spec) == "~=3.14,>4,<7,!=3.8.0"


def test_tighter_lower_bound_any():
    spec = SpecifierSet(">=0")
    lower_bound = Version("3.8.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet(">=3.8.0")


def test_tighter_lower_bound_leaves_other_restrictions():
    spec = SpecifierSet(">=1.0,!= 1.3.4.*,< 2.0")
    lower_bound = Version("1.4.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet(">=1.4.0,!=1.3.4.*,<2.0")


def test_tighter_lower_bound_adds_lower_bound_if_not_present():
    spec = SpecifierSet("!=1.3.4.*,<2.0")
    lower_bound = Version("1.4.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet("!=1.3.4.*,<2.0,>=1.4.0")


def test_tighter_lower_bound_rejects_incompatible_restrictions():
    spec = SpecifierSet(">=1.0,<2.0")
    lower_bound = Version("2.0.0")

    with pytest.raises(ValueError):
        tighten_lower_bound(spec, lower_bound)
