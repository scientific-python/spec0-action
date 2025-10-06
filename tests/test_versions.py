from packaging.version import Version
from spec0_action.versions import repr_spec_set, tighten_lower_bound
from packaging.specifiers import SpecifierSet


def test_repr_specset():
    spec = SpecifierSet("<7,!=3.8.0,>4,~=3.14")
    assert repr_spec_set(spec) == "~=3.14,>4,<7,!=3.8.0"


def test_tighter_lower_bound_any():
    spec = SpecifierSet(">=0")
    lower_bound = Version("3.8.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet(">=3.8.0")


def test_tighter_lower_bound_leaves_other_restrictions():
    spec = SpecifierSet("~= 0.9,>=1.0,!= 1.3.4.*,< 2.0")
    lower_bound = Version("3.8.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet("~= 0.9,>=3.8.0,!=1.3.4.*,<2.0")


def test_tighter_lower_bound_adds_lower_bound_if_not_present():
    spec = SpecifierSet("~=0.9,!=1.3.4.*,<2.0")
    lower_bound = Version("3.8.0")
    tightened = tighten_lower_bound(spec, lower_bound)
    assert tightened == SpecifierSet("~= 0.9,  != 1.3.4.*, < 2.0, >=3.8.0")
