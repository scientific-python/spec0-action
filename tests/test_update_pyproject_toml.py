import datetime

import pytest

from spec0_action.parsing import read_schedule, read_toml
from spec0_action import update_pyproject_toml

# Fixed time to avoid test results changing over time...
FAKE_TIME = datetime.datetime(2025, 10, 30, 0, 0, 0, tzinfo=datetime.UTC)

@pytest.fixture
def patch_datetime_now(monkeypatch):

    class mydatetime(datetime.datetime):
        @classmethod
        def now(cls, *args, **kwds):
            return FAKE_TIME

    monkeypatch.setattr(datetime, 'datetime', mydatetime)


def test_update_pyproject_toml(patch_datetime_now):
    expected = read_toml("tests/test_data/pyproject_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject.toml")
    test_schedule = read_schedule("tests/test_data/test_schedule.json")
    update_pyproject_toml(pyproject_data, test_schedule)

    assert pyproject_data == expected


def test_update_pyproject_toml_with_pixi():
    expected = read_toml("tests/test_data/pyproject_pixi_updated.toml")
    pyproject_data = read_toml("tests/test_data/pyproject_pixi.toml")
    test_schedule = read_schedule("tests/test_data/test_schedule.json")
    update_pyproject_toml(pyproject_data, test_schedule)

    assert pyproject_data == expected
