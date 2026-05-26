"""Shared creation form configuration for snippet and chooser viewsets."""

from __future__ import annotations

from typing import Any

TREEBEARD_TREE_FIELD_EXCLUDE = ("path", "depth", "numchild")


class TreebeardCreationFormMixin:
    """
    Shared form configuration for treebeard snippet admin and chooser creation.

    Set :attr:`chooser_creation_form_class` on the snippet viewset to opt in to inline
    chooser creation (browse "Add …" actions and chooser ``create/`` URLs). Use a
    ``ModelForm`` subclass of :class:`~wagtail_treebeard.forms.WagtailTreebeardAdminModelForm`
    when the parent must be supplied for child creates. Panels on the main snippet
    admin are not reused automatically.
    """

    chooser_creation_form_class = None

    def get_treebeard_exclude_form_fields(self) -> list[str]:
        exclude = list(super().get_exclude_form_fields() or [])
        for field_name in TREEBEARD_TREE_FIELD_EXCLUDE:
            if field_name not in exclude:
                exclude.append(field_name)
        return exclude

    def get_exclude_form_fields(self):
        return self.get_treebeard_exclude_form_fields()

    def get_chooser_creation_form_fields(self) -> dict[str, Any]:
        """
        Keyword arguments for :class:`~wagtail_treebeard.choosers.viewsets.ChooserViewSet`.

        Empty when :attr:`chooser_creation_form_class` is unset (chooser creation off).
        """
        if self.chooser_creation_form_class is None:
            return {}
        return {"creation_form_class": self.chooser_creation_form_class}
