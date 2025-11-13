from spec0_action.parsing import read_schedule, read_toml
from spec0_action import update_pyproject_toml


def test_update_pyproject_toml():
    expected = read_toml("tests/test_data/pyproject_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject.toml")
    test_schedule = read_schedule("tests/test_data/test_schedule.json")
    update_pyproject_toml(pyproject_data, test_schedule)

    assert pyproject_data == expected
