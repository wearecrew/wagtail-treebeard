# Contributing

Thank you for contributing to wagtail-treebeard. Tooling and CI follow the [Wagtail package maintenance guidelines](https://github.com/wagtail/wagtail/blob/main/docs/contributing/package_guidelines.md) and common patterns from the [cookiecutter-wagtail-package](https://github.com/wagtail/cookiecutter-wagtail-package) template (nightly `main`, tox matrix, pre-commit, trusted publishing).

For architecture, invariants, and agent-oriented notes, see [AGENTS.md](AGENTS.md).

## Local setup

Install [just](https://just.systems/man/en/packages.html) (task runner), then:

```bash
git clone https://github.com/wearecrew/wagtail-treebeard.git
cd wagtail-treebeard
python -m pip install -U flit tox pre-commit
pre-commit install
just build
just test
```

The interactive test project (superuser `admin` / `changeme`):

```bash
just interactive
# or: tox -e interactive
```

Open http://localhost:8020/admin/ after the server starts.

## Common commands

Run `just` (or `just --list`) to see all recipes:

```bash
just                # list recipes
just lint           # pre-commit on all files
just test           # one representative tox env
just test-one tests.test_views.TreebeardAdminViewTests  # focused run
just test-ci        # full tox matrix (release-style)
just test-future    # Wagtail main branch
just coverage       # combine .coverage.* from tox
just migrate        # sync DB after switching branches
just shell          # Django shell for the test project
```

## Tests

Tests live under `tests/` and run via Django’s test runner inside `tests/manage.py` (see `tox.ini`). Add or extend modules there for new behaviour.

Run everything locally:

```bash
just test-ci
```

Run a single environment, for example:

```bash
tox -e py3.13-django5.2-wagtail74
```

If migrations look stale after checking out another branch:

```bash
just migrate
```

## Continuous integration

On every push and pull request, GitHub Actions runs two workflows in parallel:

- **Lint** — pre-commit (Ruff and standard hooks);
- **Test** — tox across supported Python / Django / Wagtail combinations, optional **Wagtail main** (`wagtailmain`, allowed to fail on PRs), and a combined **coverage** report.

A **nightly** workflow (Mondays 03:00 UTC) tests against [Wagtail `main`](https://github.com/wagtail/wagtail); configure `SLACK_WEBHOOK_URL` in repository secrets for failure notifications.

## Pull requests

- Target `main` with a clear summary and test notes.
- Keep changes focused; match existing style (Ruff, import layout).
- Update `CHANGELOG.md` under **Unreleased** for user-visible changes.

## Releases

1. Bump the version in `src/wagtail_treebeard/__version__.py` and update `CHANGELOG.md`.
2. Merge to `main`.
3. Create a GitHub **release** (tag + notes). CI runs tests, then publishes to PyPI via trusted publishing (`publish` environment).
