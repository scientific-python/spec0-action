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
    # Day 3 of each quarter.
Allows one day buffer after the quarterly schedule release on day 1
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
      - uses: scientific-python/spec0-action@7c875bc60508e9aab2bdb851e99bfcc53b283e94 # v1.6
        with:
          update_all: 2 # also bump non-SPEC0 deps older than 2 years
```

No PAT required.
The built-in `GITHUB_TOKEN` is used by default as long as the workflow has `pull-requests: write` permission.

### Parameters

| Input                 | Required | Default                                                       | Description                                                                                                                                                      |
| --------------------- | -------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `token`               | no       | `GITHUB_TOKEN`                                                | Token with `pull-requests: write` permission to open PRs                                                                                                         |
| `project_file_name`   | no       | `pyproject.toml`                                              | Path to the file to update, relative to repository root                                                                                                          |
| `schedule_path`       | no       | —                                                             | Path to a custom `schedule.json`, relative to repository root. Uses the latest release if unset                                                                  |
| `target_branch`       | no       | `main`                                                        | Branch to open the PR against                                                                                                                                    |
| `create_pr`           | no       | `true`                                                        | Set to `false` for a dry run                                                                                                                                     |
| `pr_title`            | no       | `chore: Drop support for unsupported packages conform SPEC 0` | Title of the opened PR                                                                                                                                           |
| `commit_msg`          | no       | `chore: Drop support for unsupported packages conform SPEC 0` | Commit message for the version update commit                                                                                                                     |
| `update_all`          | no       | —                                                             | If set to N years, update PEP dependencies without a schedule floor or custom core-package policy to the oldest stable version first released within that window |
| `spec0_support_years` | no       | —                                                             | Override the support period for SPEC 0 core packages using current PyPI release history (e.g. `3`); Python still follows the supplied schedule                   |
| `excluded_packages`   | no       | —                                                             | Comma- or whitespace-separated package names to leave unchanged, including with `update_all`                                                                     |

For examples of before/after see [tests/test_data/pyproject.toml](./tests/test_data/pyproject.toml) and [tests/test_data/pyproject_updated.toml](./tests/test_data/pyproject_updated.toml).

SPEC 0 packages include `ipython`, `matplotlib`, `networkx`, `numpy`, `pandas`, `scikit-image`, `scikit-learn`, `scipy`, `xarray`, and `zarr`.

### Excluding packages

To keep a package's lower bound as-is, for example to stay compatible with NumPy 1.26 while everything else updates, list it in `excluded_packages` before the action raises its bound (bounds are never lowered).
Separate names with commas or whitespace; `python` excludes the Python requirement:

```yaml
with:
  update_all: 2
  excluded_packages: |
    numpy, scikit-learn
    python
```

Exclusions win over the schedule, `spec0_support_years`, and `update_all`, and excluded packages cause no PyPI lookup.
The CLI takes the same value via `--excluded-packages`.

### Changing the core-package support period

The supplied schedule gives SPEC 0 packages two years of support.
To use three years for those packages while updating other dependencies independently:

```yaml
with:
  spec0_support_years: 3
  update_all: 2
```

For each release (`X.Y.0`; pre-, post-, and patch releases are ignored), support ends at the start of the quarter containing its release date plus the period, and the floor moves to the next release.
The schedule generator and custom support periods use the earliest PyPI upload of a release, whether a source distribution or wheel; later uploads do not reset its age.
Floors come from the PyPI release history, so any explicit value, can differ from a published schedule snapshot.
Python always follows the schedule.

Precedence is `excluded_packages`, then `spec0_support_years` for SPEC 0 packages, then the schedule, then `update_all` for the remaining PEP dependencies.
If PyPI cannot be reached, the affected dependency stays unchanged with a warning rather than falling back to the schedule or `update_all`.

The CLI takes `--spec0-support-years 3` and the Python API `spec0_support_years=3`.
Extras such as `xarray[io]>=2026.5.1` and environment markers are preserved when bounds change.

## Limitations

1. The action only tightens lower bounds and leaves upper bounds untouched.
   A proposed floor that conflicts with an existing constraint is skipped; for example, `numpy = ">=1.25.0,<2"` stays unchanged when the proposed floor is `2.0.0`.
   It does not solve the full dependency graph or guarantee a compatible environment.
2. Only `pyproject.toml` is currently supported.
   This includes Pixi tables within the file; standalone Conda environment files are unsupported.
   Conda-only version expressions such as `>=1.26|>=2.0` are left unchanged.

## Maintainer notes

### Releasing a new action version

Action versions are **git tags only**, do not create a GitHub Release for them.
GitHub Releases in this repository are reserved for the quarterly schedule data.

```bash
git tag v1.x
git push origin v1.x
```

### Schedule releases

The SPEC 0 schedule (`schedule.json` and `schedule.md`) is published as a GitHub Release quarterly by the [Update SPEC 0 schedule](./.github/workflows/update_schedule.yml) workflow.
Releases are tagged `schedule-YYYY-QN` (e.g. `schedule-2026-Q2`).

The action always fetches `schedule.json` from the **latest** GitHub Release in this repository, which will always be a schedule release as long as action versions are never published as releases.

#### Bootstrap

Before the first quarterly schedule release exists, the action will fail.
To create the initial release, trigger the workflow manually:

1. Go to **Actions → Update SPEC 0 schedule**
2. Click **Run workflow**

Subsequent releases are created automatically on the 1st of January, April, July, and October.
