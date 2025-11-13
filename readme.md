# SPEC 0 Versions Action

This repository contains a Github Action to update Python dependencies in your `pyproject.toml` such that they conform to the SPEC 0 support schedule. You can find this schedule [here](https://scientific-python.org/specs/spec-0000/)

## Using the action


### Example workflow

To use the action you can copy the yaml below, and paste it into `.github/workflows/update-spec0.yaml`. Whenever the action is triggered it will open a PR in your repository that will update the dependencies of SPEC 0 to the new lower bound. For this you will have to provide it with a PAT that has write permissions in the `contents` and `pull request` scopes. Please refer to the GitHub documentation for instructions on how to do this [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).


```yaml
name: Update SPEC 0 dependencies

on:
  schedule:
    # At 00:00 on day-of-month 3 in every 3rd month. (i.e. every quarter)
    # Releases should happen on the second day of the quarter in savente93/SPEC0-schedule to 
    # avoid fence post errors, so allow one day as a buffer to avoid timing issues here as well.
    - cron: "0 0 3 */3 *"
  # On demand: 
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: savente93/update-spec0-dependencies@v1.0.0
        with:
          token: ${{ secrets.GH_PAT }} # <- GH_PAT you will have to configure in the repo as a secret
```

It should update any of the packages listed in the `dependency`, or `tool.pixi.*` tables. For examples of before and after you can see [./tests/test_data/pyproject.toml](./tests/test_data/pyproject.toml) and [./tests/test_data/pyproject_updated.toml](./tests/test_data/pyproject_updated.toml) respectively. Other tools are not yet supported, but I am open to feature requests.

The newest lower bounds will be downloaded from [https://github.com/savente93/SPEC0-schedule](https://github.com/savente93/SPEC0-schedule) but you should not have to worry about this. 


### Parameters

| Input               | Required | Default            | Description                                                                    |
| ------------------- | -------- | ------------------ | -------------------------------------------------------------------------------|
| token               | yes      | —                  | Personal access token with `contents` & `pull-request` scopes                  |
| project\_file\_name | no       | `"pyproject.toml"` | File to update dependencies in                                                 |
| schedule\_path      | no       | `"schedule.json"`  | path to schedule json data. only relevant if you have it committed in your repo |
| target\_branch      | no       | `"main"`           | Branch to open PR against                                                      |
| create_pr           | no       | `true`             | Open a PR with new versions                                                    |
| pr_title            | no       | `chore: Drop support for unsupported packages conform SPEC 0`             | The title of the PR that will be opened                                                    |
| commit_msg            | no       | `chore: Drop support for unsupported packages conform SPEC 0`             | Commit message of the commit to update the versions.                                                     |


## Limitations

1. Since this action simply parses the toml to do the upgrade and leaves any other bounds intact, it is possible that the environment of the PR becomes unsolvable.
   For example if you have a numpy dependency like so: `numpy = ">=1.25.0,<2"` this will get updated in the PR to `numpy = ">=2.0.0,<2"` which is infeasible. 
   Keeping the resulting environment solvable is outside the scope of this action, so you might have to adjust them manually.
2. Currently only `pyproject.toml` is supported by this action, though other manifest files could be considered upon request. 

