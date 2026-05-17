# Contributing

Thank you for contributing to wagtail-treebeard. Tooling and CI follow the [Wagtail package maintenance guidelines](https://github.com/wagtail/wagtail/blob/main/docs/contributing/package_guidelines.md) and common patterns from the [cookiecutter-wagtail-package](https://github.com/wagtail/cookiecutter-wagtail-package) template (nightly `main`, tox matrix, pre-commit, trusted publishing).

## Local setup

```bash
git clone https://github.com/torchbox/wagtail-treebeard.git
cd wagtail-treebeard
python -m pip install -U flit tox pre-commit
pre-commit install
make build
make test
```

The interactive test project (superuser `admin` / `changeme`):

```bash
make interactive
# or: tox -e interactive
```

## Common commands

```bash
make help           # list tasks
make lint           # pre-commit on all files
make test           # one representative tox env
make test-ci        # full tox matrix (release-style)
make test-future    # Wagtail main branch
make coverage       # combine .coverage.* from tox
```

## Tests

Tests live under `tests/` and run via Django’s test runner inside `tests/manage.py` (see `tox.ini`). Add or extend modules there for new behaviour.

Run everything locally:

```bash
make test-ci
```

Run a single environment, for example:

```bash
tox -e py3.13-django5.2-wagtail74
```

## Continuous integration

On every push and pull request, GitHub Actions:

- runs **pre-commit** (Ruff and standard hooks);
- runs **tox** across supported Python / Django / Wagtail combinations;
- runs **Wagtail main** (`wagtailmain`) as an allowed-to-fail check on PRs;
- publishes a combined **coverage** report.

A **nightly** workflow (Mondays 03:00 UTC) tests against [Wagtail `main`](https://github.com/wagtail/wagtail); configure `SLACK_WEBHOOK_URL` in repository secrets for failure notifications.

## Pull requests

- Target `main` with a clear summary and test notes.
- Keep changes focused; match existing style (Ruff, import layout).
- Update `CHANGELOG.md` under **Unreleased** for user-visible changes.

## Releases

1. Bump the version in `src/wagtail_treebeard/__version__.py` and update `CHANGELOG.md`.
2. Merge to `main`.
3. Create a GitHub **release** (tag + notes). CI runs tests, then publishes to PyPI via trusted publishing (`publish` environment).
