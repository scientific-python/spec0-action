from packaging.version import Version
from packaging.specifiers import Specifier, SpecifierSet


def tighten_lower_bound(
    spec_set: SpecifierSet, new_lower_bound: Version
) -> SpecifierSet:
    out = []
    contains_lower_bound = False

    for spec in spec_set:
        if spec.operator not in [">", ">="]:
            out.append(spec)
            continue
        if new_lower_bound in spec:
            out.append(Specifier(f">={new_lower_bound}"))
            contains_lower_bound = True
        else:
            raise ValueError(f"{spec} is already stricter than {new_lower_bound}")

    if not contains_lower_bound:
        out.append(Specifier(f">={new_lower_bound}"))

    return SpecifierSet(out)


def repr_spec_set(spec: SpecifierSet) -> str:
    return ",".join(sorted(map(str, spec), reverse=True)).replace(" ", "")
