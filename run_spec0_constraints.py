import datetime
import json
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

from spec0_action import read_schedule
from spec0_action.constraints import ScheduleError, format_constraints, minimum_versions


def parse_date(value: str) -> datetime.datetime:
    try:
        date = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"reference date must look like YYYY-MM-DD, got {value!r}"
        ) from exc
    return datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.UTC)


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(
        description="Write exact SPEC 0 minimum version pins to a constraints file, to test the oldest supported versions in CI.",
    )
    parser.add_argument("schedule_path", help="Path to the schedule json payload.")
    parser.add_argument(
        "--packages",
        required=True,
        metavar="NAMES",
        help="Comma- or whitespace-separated packages to pin, e.g. 'numpy scipy pandas'. Include python to also report its minimum version.",
    )
    parser.add_argument(
        "--output",
        default="constraints-spec0.txt",
        help="Where to write the constraints file. Defaults to 'constraints-spec0.txt'.",
    )
    parser.add_argument(
        "--reference-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date the floors are computed for. Defaults to today (UTC).",
    )
    args = parser.parse_args(argv)

    schedule_path = Path(args.schedule_path)
    if not schedule_path.exists():
        raise ValueError(
            f"{schedule_path} was supplied as path to schedule file but it did not exist"
        )
    if args.reference_date:
        reference_date = parse_date(args.reference_date)
    else:
        reference_date = datetime.datetime.now(datetime.UTC)

    try:
        versions = minimum_versions(
            read_schedule(schedule_path), args.packages, reference_date
        )
    except ScheduleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    output = Path(args.output)
    output.write_text(format_constraints(versions))
    mapping = {package: str(version) for package, version in versions.items()}
    print(f"Wrote {output}:")
    print(output.read_text(), end="")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as file:
            file.write(f"constraints_file={output}\n")
            file.write(f"versions={json.dumps(mapping)}\n")
            file.write(f"python_version={mapping.get('python', '')}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
