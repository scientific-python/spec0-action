from packaging.specifiers import Specifier, SpecifierSet
from packaging.version import Version


def tighten_lower_bound(
    spec_set: SpecifierSet, new_lower_bound: Version
) -> SpecifierSet | None:
    """
    Return ``spec_set`` with its lower bound raised to ``new_lower_bound``.

    Returns None when the new bound does not satisfy ``spec_set`` (the existing
    bounds are already tighter or conflict with it).
    """
    if new_lower_bound not in spec_set:
        return None

    return SpecifierSet(
        [spec for spec in spec_set if spec.operator not in {">", ">="}]
        + [Specifier(f">={new_lower_bound}")]
    )


def repr_spec_set(spec: SpecifierSet) -> str:
    return ",".join(sorted(map(str, spec), reverse=True)).replace(" ", "")
