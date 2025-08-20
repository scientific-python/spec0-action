# SPEC-0 Versions Action

This repository contains a Github Action to update Python dependencies such that they conform to the SPEC 0 support schedule.
It also contains released versions of the schedule in various formats that that action can use to open PRs in your repository.

## Using the action

To use the action you can copy the yaml below, and paste it into `.github/workflows/update-spec-0.yaml`.
The arguments below are filled with their default value, in most cases you won't have to fill them.
All except for `token` are optional. 

Whenever the action is triggered it will open a PR in your repository that will update the dependencies of SPEC 0 to the new lower bound.
For this you will have to provide it with a PAT that has write permissions in the `contents` and `pull request` scopes.
Please refer to the GitHub documentation for instructions on how to do this [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).


```yaml
name: Update SPEC 0 dependencies

on:
  workflow_dispatch:
  schedule:
    # At 00:00 on day-of-month 2 in every 3rd month. (i.e. every quarter)
    # Releases should happen on the first day of the month in scientific-python/spec-zero-tools
    # so allow one day as a buffer to avoid timing issues
    - cron: "0 0 2 */3 *"

permissions:
    contents: write
    pull-requests: write

jobs:
    update:
    runs-on: ubuntu-latest
    steps:
      - uses: scientific-python/spec0-action@v1
    with: 
        token: ${{ secrets.GH_PAT }}
        project_file_name: "pyproject.toml"
        target_branch: 'main'
```

It should update any of the packages listed in the `dependency`, or `tool.pixi.*` tables. 

## Limitations

1. Since this action simply parses the toml to do the upgrade and leaves any other bounds intact, it is possible that the environment of the PR becomes unsolvable.
   For example if you have a numpy dependency like so: `numpy = ">=1.25.0,<2"` this will get updated in the PR to `numpy = "2.0.0,<2"` which is infeasible. 
   Keeping the resulting environment solvable is outside the scope of this action, so you might have to be adjusted manually.
2. Currently only `pyproject.toml` is supported by this action, though other manifest files could be considered upon request. 

