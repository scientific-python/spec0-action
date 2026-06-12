# SPEC 0 Versions Action

A GitHub Action that updates the lower bounds of Python dependencies in `pyproject.toml` to conform to the [SPEC 0 support schedule](https://scientific-python.org/specs/spec-0000/).

## Using the action

### Example workflow

Copy the yaml below into `.github/workflows/update-spec0.yaml`.
On each run the action opens a PR updating dependency lower bounds to match the current SPEC 0 schedule.

```yaml
name: Update SPEC 0 dependencies

on:
  schedule:
    # Day 3 of each quarter. Allows one day buffer after the quarterly schedule release on day 1
    - cron: "0 0 3 1,4,7,10 *"
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

concurrency:
  group: ${{ github.workflow }}
  cancel-in-progress: true

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: scientific-python/spec0-action@8b8b76f254aecce36e6f07de7dde174cb3cafa81 # v1.3
        with:
          update_all: 2 # also bump non-SPEC0 deps older than 2 years
```

No PAT required.
The built-in `GITHUB_TOKEN` is used by default as long as the workflow has `pull-requests: write` permission.

### Parameters

| Input               | Required | Default                                                       | Description                                                                                                      |
| ------------------- | -------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `token`             | no       | `GITHUB_TOKEN`                                                | Token with `pull-requests: write` permission to open PRs                                                         |
| `project_file_name` | no       | `pyproject.toml`                                              | Path to the file to update, relative to repository root                                                          |
| `schedule_path`     | no       | —                                                             | Path to a custom `schedule.json`, relative to repository root. Uses the latest release if unset                  |
| `target_branch`     | no       | `main`                                                        | Branch to open the PR against                                                                                    |
| `create_pr`         | no       | `true`                                                        | Set to `false` for a dry run                                                                                     |
| `pr_title`          | no       | `chore: Drop support for unsupported packages conform SPEC 0` | Title of the opened PR                                                                                           |
| `commit_msg`        | no       | `chore: Drop support for unsupported packages conform SPEC 0` | Commit message for the version update commit                                                                     |
| `update_all`        | no       | —                                                             | If set to a number N, also update non-SPEC0 dependencies to versions released within the last N years (e.g. `2`) |

For examples of before/after see [tests/test_data/pyproject.toml](./tests/test_data/pyproject.toml) and [tests/test_data/pyproject_updated.toml](./tests/test_data/pyproject_updated.toml).

## Limitations

1. The action only tightens lower bounds and leaves upper bounds untouched. An update can produce an unsolvable environment — for example `numpy = ">=1.25.0,<2"` becomes `numpy = ">=2.0.0,<2"`. Keeping the environment solvable is out of scope; adjust upper bounds manually if needed.
2. Only `pyproject.toml` is currently supported.

## Maintainer notes

### Releasing a new action version

Action versions are **git tags only**, do not create a GitHub Release for them. GitHub Releases in this repository are reserved for the quarterly schedule data.

```bash
git tag v1.x
git push origin v1.x
```

### Schedule releases

The SPEC 0 schedule (`schedule.json` and `schedule.md`) is published as a GitHub Release quarterly by the [Update SPEC 0 schedule](./.github/workflows/update_schedule.yml) workflow. Releases are tagged `schedule-YYYY-QN` (e.g. `schedule-2026-Q2`).

The action always fetches `schedule.json` from the **latest** GitHub Release in this repository, which will always be a schedule release as long as action versions are never published as releases.

#### Bootstrap

Before the first quarterly schedule release exists, the action will fail. To create the initial release, trigger the workflow manually:

1. Go to **Actions → Update SPEC 0 schedule**
2. Click **Run workflow**

Subsequent releases are created automatically on the 1st of January, April, July, and October.
