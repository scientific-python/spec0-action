from argparse import ArgumentParser
from pathlib import Path

from spec0_action import read_schedule, read_toml, update_pyproject_toml, write_toml

if __name__ == "__main__":
    parser = ArgumentParser(
        description="A script to update your project dependencies to be in line with the scientific python SPEC 0 support schedule",
    )
    parser.add_argument(
        "toml_path",
        default="pyproject.toml",
        help="Path to the project file that lists the dependencies. defaults to 'pyproject.toml'.",
    )
    parser.add_argument(
        "schedule_path",
        default="schedule.json",
        help="Path to the schedule json payload. defaults to 'schedule.json'",
    )
    parser.add_argument(
        "--update-all",
        type=float,
        default=None,
        metavar="YEARS",
        help="Also update all non-SPEC0 dependencies to versions released within the last YEARS years (e.g., 2).",
    )
    parser.add_argument(
        "--excluded-packages",
        default="",
        metavar="NAMES",
        help="Leave these comma- or whitespace-separated package names unchanged; use python to exclude Python requirements.",
    )
    args = parser.parse_args()
    toml_path = Path(args.toml_path)
    schedule_path = Path(args.schedule_path)
    if not toml_path.exists():
        raise ValueError(
            f"{toml_path} was supplied as path to project file but it did not exist"
        )
    if not schedule_path.exists():
        raise ValueError(
            f"{schedule_path} was supplied as path to schedule file but it did not exist"
        )
    project_data = read_toml(toml_path)
    schedule_data = read_schedule(schedule_path)
    update_pyproject_toml(
        project_data,
        schedule_data,
        update_all=args.update_all,
        excluded_packages=args.excluded_packages.replace(",", " ").split(),
    )
    write_toml(toml_path, project_data)
