# wagtail-treebeard development commands.
# Install: https://just.systems/man/en/packages.html — then run `just` to list recipes.

default:
    @just --list

# Build a wheel (used by tox and CI).
build:
    python -Im flit build --format wheel

# Run pre-commit on all files.
lint:
    pre-commit run --all-files

# Run a single representative tox environment.
test:
    tox -e py3.13-django5.2-wagtail74

# Run specific tests, e.g. `just test-one tests.test_views -k reorder`
test-one *args:
    tox -e py3.13-django5.2-wagtail74 -- {{args}}

# Run the full tox matrix (builds wheel first).
test-ci: build
    tox --installpkg ./dist/*.whl

# Test against Wagtail main (nightly / compatibility).
test-future:
    tox -e wagtailmain

# Combine coverage data from tox runs.
coverage:
    tox -e coverage-report

# Interactive test project at http://localhost:8020/admin/ (admin / changeme).
interactive:
    tox -e interactive

# Sync the test DB after switching branches.
migrate:
    tox exec -e py3.13-django5.2-wagtail74 -- python tests/manage.py migrate --run-syncdb

# Django shell for the test project.
shell:
    tox exec -e py3.13-django5.2-wagtail74 -- python tests/manage.py shell

# Remove Python cache files.
clean-pyc:
    find . -name '*.pyc' -exec rm -f {} +
    find . -name '*.pyo' -exec rm -f {} +
    find . -name '*~' -exec rm -f {} +
