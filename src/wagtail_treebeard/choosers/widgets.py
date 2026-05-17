from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django import forms
from django.utils.functional import cached_property
from wagtail.admin.staticfiles import versioned_static
from wagtail.snippets.widgets import AdminSnippetChooser

from .constants import ChooserMode


class TreebeardModelChooser(AdminSnippetChooser):
    """Snippet chooser with hierarchical browse and optional search (see :class:`~wagtail_treebeard.chooser.TreebeardChooserViewSet`)."""

    def __init__(
        self,
        model: type,
        *,
        chooser_mode: ChooserMode = ChooserMode.CHOOSE,
        move_instance_pk: int | str | None = None,
        **kwargs: Any,
    ) -> None:
        self.chooser_mode = chooser_mode
        self.move_instance_pk = move_instance_pk
        super().__init__(model, **kwargs)

    def get_chooser_modal_url(self) -> str:
        params: dict[str, str] = {}
        if self.chooser_mode is not ChooserMode.CHOOSE:
            params["chooser_mode"] = self.chooser_mode
        if self.move_instance_pk is not None:
            params["move_instance_pk"] = str(self.move_instance_pk)
        if self.chooser_mode is ChooserMode.PARENT_FOR_CREATE and getattr(
            self, "show_choose_root_option", False
        ):
            params["show_choose_root_option"] = "1"
        base = super().get_chooser_modal_url()
        if not params:
            return base
        return f"{base}?{urlencode(params)}"

    @cached_property
    def media(self):
        return forms.Media(
            js=[
                *super().media._js,
                versioned_static("wagtail_treebeard/js/treebeard-snippet-chooser.js"),
            ]
        )


class TreebeardParentChooser(TreebeardModelChooser):
    """
    Pick a parent for create.

    Set ``show_choose_root_option=True`` to show “Create as root (no parent)” in the modal
    when the user has ``add_root``. Off by default so pages that already offer root
    creation (e.g. :class:`~wagtail_treebeard.views.ConfirmAddPositionView`) stay unambiguous.
    """

    def __init__(
        self, model: type, *, show_choose_root_option: bool = False, **kwargs: Any
    ) -> None:
        self.show_choose_root_option = show_choose_root_option
        super().__init__(model, chooser_mode=ChooserMode.PARENT_FOR_CREATE, **kwargs)


class TreebeardMoveParentChooser(TreebeardModelChooser):
    """
    Pick a new parent when moving an existing node.

    Browse shows the tree (minus the node being moved); each row uses ``can_move_to``. Search
    lists ``instances_user_can_move_to`` (the same rules, fetched once as a queryset).
    """

    def __init__(
        self, model: type, *, move_instance_pk: int | str, **kwargs: Any
    ) -> None:
        super().__init__(
            model,
            chooser_mode=ChooserMode.PARENT_FOR_MOVE,
            move_instance_pk=move_instance_pk,
            **kwargs,
        )
