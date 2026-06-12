from packaging.version import Version
from packaging.specifiers import Specifier, SpecifierSet


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

    out = []
    contains_lower_bound = False

    for spec in spec_set:
        if spec.operator in (">", ">="):
            # new_lower_bound satisfies every specifier in the set, so it can
            # simply replace any existing lower bound
            out.append(Specifier(f">={new_lower_bound}"))
            contains_lower_bound = True
        else:
            out.append(spec)

    if not contains_lower_bound:
        out.append(Specifier(f">={new_lower_bound}"))

    return SpecifierSet(out)


def repr_spec_set(spec: SpecifierSet) -> str:
    return ",".join(sorted(map(str, spec), reverse=True)).replace(" ", "")
