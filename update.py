from spec0_action import update_pyproject_toml, read_toml, write_toml, read_schedule
from pathlib import Path
from argparse import ArgumentParser


if __name__ == '__main__':

    parser = ArgumentParser(
                        prog='spec_zero_update',
                        description='A script to update your project dependencies to be in line with the scientific python SPEC 0 support schedule',
                        )

    parser.add_argument('toml_path', default="pyproject.toml", help="Path to the project file that lists the dependencies. defaults to 'pyproject.toml'.")           
    parser.add_argument('schedule_path', default="schedule.json", help="Path to the schedule json payload. defaults to 'schedule.json'")           

    args = parser.parse_args()

    toml_path = Path(args.toml_path)
    schedule_path = Path(args.schedule_path)

    if not toml_path.exists():
        raise ValueError(f"{toml_path} was supplied as path to project file but it did not exist")

    project_data = read_toml(toml_path)
    schedule_data = read_schedule(schedule_path)
    update_pyproject_toml(project_data, schedule_data)

    write_toml(toml_path, project_data)
