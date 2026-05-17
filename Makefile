.PHONY: help clean-pyc lint test test-ci test-future coverage interactive build
.DEFAULT_GOAL := help

help: ## List available commands.
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36mmake %-18s\033[0m %s\n", $$1, $$2}'

clean-pyc: ## Remove Python cache files.
	find . -name '*.pyc' -exec rm -f {} +
	find . -name '*.pyo' -exec rm -f {} +
	find . -name '*~' -exec rm -f {} +

build: ## Build a wheel (used by tox and CI).
	python -Im flit build --format wheel

lint: ## Run pre-commit on all files.
	pre-commit run --all-files

test: ## Run a single representative tox environment.
	tox -e py3.13-django5.2-wagtail74

test-ci: build ## Run the full tox matrix.
	tox --installpkg ./dist/*.whl

test-future: ## Test against Wagtail main (nightly / compatibility).
	tox -e wagtailmain

coverage: ## Combine coverage data from tox runs.
	tox -e coverage-report

interactive: ## Run the interactive test project (admin / changeme).
	tox -e interactive
