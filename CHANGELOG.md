# Changelog

## Unreleased

### Added

- Initial release of wagtail-treebeard snippet admin for django-treebeard `MP_Node` models.
- `Makefile`, `CONTRIBUTING.md`, and nightly CI against Wagtail `main` (Wagtail add-on package conventions).

### Changed

- Require Python 3.12+ and Wagtail 7.3+ (APIs used on create and custom URL patterns). Wagtail 6.x and 5.x are not supported.
- Require Django 5.2+; Django 4.2 and 5.0 are no longer supported or tested.
- CI: separate Lint and Test workflows, tox matrix across Wagtail 7.3 / 7.4, optional `wagtailmain` on PRs, publish gated on tests.
