from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import forms
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from django.db import models

from wagtail.admin.forms.models import WagtailAdminModelForm

from wagtail_treebeard.choosers.widgets import (
    TreebeardMoveParentChooser,
    TreebeardParentChooser,
)


class WagtailTreebeardAdminModelForm(WagtailAdminModelForm):
    """
    Base for forms on :class:`~wagtail_treebeard.models.TreebeardMixin` models
    registered with :class:`~wagtail_treebeard.viewsets.WagtailTreebeardSnippetViewSet`.

    Accepts ``parent`` (the node chosen in the admin before create) so create forms can mirror
    edit-time behaviour that depends on the parent, even when ``instance.pk`` is not set yet.
    """

    def __init__(self, *args: Any, parent: Any | None = None, **kwargs: Any) -> None:
        self.parent = parent
        super().__init__(*args, **kwargs)


class ConfirmAddPositionForm(forms.Form):
    def __init__(
        self,
        *args: Any,
        model: type[models.Model],
        parent_queryset: models.QuerySet,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["parent"] = forms.ModelChoiceField(
            label=_("Choose a parent"),
            required=True,
            queryset=parent_queryset,
            widget=TreebeardParentChooser(model=model),
        )


class MoveForm(forms.Form):
    def __init__(
        self,
        *args: Any,
        model: type[models.Model],
        parent_queryset: models.QuerySet,
        move_instance_pk: int | str,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["new_parent"] = forms.ModelChoiceField(
            label=_("Choose a new parent"),
            required=True,
            queryset=parent_queryset,
            widget=TreebeardMoveParentChooser(
                model=model, move_instance_pk=move_instance_pk
            ),
        )
