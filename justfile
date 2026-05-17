# wagtail-treebeard development commands.
# Install: https://just.systems/man/en/packages.html and https://docs.astral.sh/uv/getting-started/installation/

# PYTHONPATH for tests/manage.py (matches tox testenv).
export PYTHONPATH := "tests:."

default:
    @just --list

# Create or update .venv with uv (package + dev tools). Point your editor at .venv/bin/python.
sync:
    uv sync

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

# Run the test project via uv (after `just sync`); admin / changeme.
run:
    uv run python tests/manage.py migrate --run-syncdb
    uv run python tests/manage.py shell -c "from django.contrib.auth.models import User; (not User.objects.filter(username='admin').exists()) and User.objects.create_superuser('admin', 'super@example.com', 'changeme')"
    uv run python tests/manage.py runserver 0.0.0.0:8020

# Sync the test DB after switching branches (uses uv venv).
migrate:
    uv run python tests/manage.py migrate --run-syncdb

# Django shell for the test project (uses uv venv).
shell:
    uv run python tests/manage.py shell

# Remove Python cache files.
clean-pyc:
    find . -name '*.pyc' -exec rm -f {} +
    find . -name '*.pyo' -exec rm -f {} +
    find . -name '*~' -exec rm -f {} +
