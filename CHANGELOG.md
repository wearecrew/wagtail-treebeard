# Changelog

## Unreleased

### Added

- Initial release of wagtail-treebeard snippet admin for django-treebeard `MP_Node` models.
- `Makefile`, `CONTRIBUTING.md`, and nightly CI against Wagtail `main` (Wagtail add-on package conventions).

### Changed

- Require Wagtail 7.0+ (snippet reorder and related admin APIs). Wagtail 6.x and 5.x are not supported.
- CI: pre-commit in the main workflow, tox matrix across Wagtail 7.0 / 7.4, optional `wagtailmain` on PRs, publish gated on tests.
