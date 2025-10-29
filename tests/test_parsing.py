from spec0_action.parsing import parse_version_spec, parse_pep_dependency
from packaging.specifiers import SpecifierSet
import pytest
from urllib.parse import urlparse


def test_parsing_correct():
    assert SpecifierSet(">=0") == parse_version_spec("*")
    assert SpecifierSet(">4,<9") == parse_version_spec(">4, <9")
    assert SpecifierSet(">=4") == parse_version_spec(">=4")
    assert SpecifierSet(">=2025.7") == parse_version_spec(">=2025.7")
    assert SpecifierSet("==3.11.*") == parse_version_spec("3.11.*")


def test_parsing_incorrect():
    with pytest.raises(ValueError):
        parse_version_spec("-18")

    with pytest.raises(ValueError):
        parse_version_spec("asdf")


def test_pep_dependency_parsing():
    matplotlib_str = "matplotlib"
    pkg, features, spec, env = parse_pep_dependency(matplotlib_str)

    assert pkg == "matplotlib", pkg
    assert features is None, features
    assert spec is None, spec
    assert env is None, env


def test_pep_dependency_parsing_with_spec_and_optional_dep():
    matplotlib_str = "matplotlib[foo,bar]>=3.7.0,<4"
    pkg, features, spec, env = parse_pep_dependency(matplotlib_str)

    assert pkg == "matplotlib", pkg
    assert features == "[foo,bar]", features
    assert spec == SpecifierSet(">=3.7.0,<4"), spec
    assert env is None, env


def test_pep_dependency_parsing_with_spec():
    matplotlib_str = "matplotlib>=3.7.0,<4"
    pkg, features, spec, env = parse_pep_dependency(matplotlib_str)

    assert pkg == "matplotlib", pkg
    assert features is None, features
    assert spec == SpecifierSet(">=3.7.0,<4"), spec
    assert env is None, env


def test_pep_dependency_parsing_with_url_spec():
    dep_str = "matplotlib @ https://github.com/pypa/pip/archive/1.3.1.zip#sha1=da9234ee9982d4bbb3c72346a6de940a148ea686"
    pkg, features, spec, env = parse_pep_dependency(dep_str)

    assert pkg == "matplotlib", pkg
    assert features is None, features
    assert spec == urlparse(
        " https://github.com/pypa/pip/archive/1.3.1.zip#sha1=da9234ee9982d4bbb3c72346a6de940a148ea686"
    ), spec
    assert env is None, env


def test_pep_dependency_parsing_extra_restrictions():
    matplotlib_str = "matplotlib>=3.7.0,<4,!=3.8.14"
    pkg, features, spec, env = parse_pep_dependency(matplotlib_str)

    assert pkg == "matplotlib", pkg
    assert features is None, features
    assert spec == SpecifierSet("!=3.8.14,<4,>=3.7.0"), spec
    assert env is None, env


def test_pep_dependency_parsing_with_environment_marker():
    matplotlib_str = "matplotlib>=3.7.0,<4;sys_platform != 'win32'"
    pkg, features, spec, env = parse_pep_dependency(matplotlib_str)

    assert pkg == "matplotlib", pkg
    assert features is None, features
    assert spec == SpecifierSet(">=3.7.0,<4"), spec
    assert env == ";sys_platform != 'win32'", env
