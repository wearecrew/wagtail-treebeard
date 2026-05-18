"""Django system checks for wagtail-treebeard."""

from __future__ import annotations

from django.apps import apps
from django.core.checks import Error, register

from wagtail_treebeard.models import TreebeardMixin
from wagtail_treebeard.utils import breadcrumb_title_lookup_error_message


@register()
def check_breadcrumb_title_fields(app_configs, **kwargs):
    errors: list[Error] = []
    for model in apps.get_models():
        if not issubclass(model, TreebeardMixin) or model._meta.abstract:
            continue
        errors.extend(_breadcrumb_title_fields_errors(model))
    return errors


def _breadcrumb_title_fields_errors(model: type) -> list[Error]:
    raw = getattr(model, "breadcrumb_title_fields", None)
    if raw is None:
        return []
    label = model._meta.label
    if not isinstance(raw, tuple):
        return [
            Error(
                f"{label}: breadcrumb_title_fields must be a tuple of field lookup "
                f"strings, not {type(raw).__name__}.",
                id="wagtail_treebeard.E001",
                obj=model,
            )
        ]
    errors: list[Error] = []
    for lookup in raw:
        if not isinstance(lookup, str):
            errors.append(
                Error(
                    f"{label}: breadcrumb_title_fields Items must be strings, "
                    f"not {type(lookup).__name__}.",
                    id="wagtail_treebeard.E002",
                    obj=model,
                )
            )
            continue
        message = breadcrumb_title_lookup_error_message(model, lookup)
        if message:
            errors.append(
                Error(
                    message,
                    id="wagtail_treebeard.E003",
                    obj=model,
                )
            )
    return errors
