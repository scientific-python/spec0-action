from packaging.version import Version
from spec0_action.versions import repr_spec_set, tighten_lower_bound
from packaging.specifiers import SpecifierSet
import pytest


def test_repr_specset():
    spec = SpecifierSet("<7,!=3.8.0,>4,~=3.14")
    assert repr_spec_set(spec) == "~=3.14,>4,<7,!=3.8.0"


@pytest.mark.parametrize(
    ("spec", "bound", "expected"),
    [
        # any-version spec gets the new floor
        (">=0", "3.8.0", ">=3.8.0"),
        # exclusive lower bound is replaced as well
        (">1.0", "1.4.0", ">=1.4.0"),
        # other restrictions are kept
        (">=1.0,!= 1.3.4.*,< 2.0", "1.4.0", ">=1.4.0,!=1.3.4.*,<2.0"),
        # floor added when absent
        ("!=1.3.4.*,<2.0", "1.4.0", "!=1.3.4.*,<2.0,>=1.4.0"),
        # compatible-release specs keep their ceiling
        ("~=1.3", "1.4.0", "~=1.3,>=1.4.0"),
        # ~= mixed with other restrictions, bound inside the compatible range
        ("~=0.9,!=0.9.4.*,<2.0", "0.9.5", "~=0.9,!=0.9.4.*,<2.0,>=0.9.5"),
        # bound outside the compatible-release range
        ("~=0.9,!=1.3.4.*,<2.0", "1.4.0", None),
        # new bound conflicts with the upper bound
        (">=1.0,<2.0", "2.0.0", None),
        # pinned versions can't be tightened
        ("==1.21.0", "2.0.0", None),
        # existing bound already stricter
        (">=2.5", "2.0.0", None),
    ],
)
def test_tighten_lower_bound(spec, bound, expected):
    result = tighten_lower_bound(SpecifierSet(spec), Version(bound))
    assert result == (None if expected is None else SpecifierSet(expected))
