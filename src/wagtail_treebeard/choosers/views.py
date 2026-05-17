"""Tree-aware snippet chooser (hierarchical browse + optional search)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from django.contrib.admin.utils import quote, unquote
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ImproperlyConfigured
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.admin.ui.tables import Column, Table
from wagtail.admin.views.generic.chooser import (
    ChooseResultsViewMixin,
    ChooseViewMixin,
    CreationFormMixin,
)
from wagtail.snippets.views.chooser import BaseSnippetChooseView

from wagtail_treebeard.utils import admin_display_title

from .constants import PRESERVED_CHOOSER_PARAMS, ChooserMode


if TYPE_CHECKING:
    from django.db import models


class ChooseResultsMixin:
    """Browse MP_Node children by default; flat search when the filter form is searching."""

    results_template_name = "wagtail_treebeard/chooser/results.html"
    preserve_url_parameters = list(PRESERVED_CHOOSER_PARAMS)
    browse_parent: models.Model | None = None
    choose_explore_results_url_name: str | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.browse_parent = None
        parent_pk = kwargs.get("parent_pk")
        if parent_pk:
            self.browse_parent = get_object_or_404(
                self.require_model_class(), pk=unquote(str(parent_pk))
            )

    def get(self, request, *args: Any, **kwargs: Any):
        # ``explore/<parent_pk>/results/`` passes parent_pk; stock chooser ``get()`` does not.
        return super().get(request)

    def can_create(self) -> bool:
        return False

    def require_model_class(self) -> type[models.Model]:
        if self.model_class is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} requires a model.")
        return self.model_class

    def can_choose_root_for_user(self, user: AbstractBaseUser) -> bool:
        return self.require_model_class().permission_policy.user_can_add_root(user)

    def show_choose_root_option_enabled(self) -> bool:
        """Whether the modal may offer “create as root (no parent)”."""
        raw = self.request.GET.get("show_choose_root_option", "0")
        return raw in ("1", "true", "True")

    @property
    def can_choose_root(self) -> bool:
        if self.get_chooser_mode() is not ChooserMode.PARENT_FOR_CREATE:
            return False
        if not self.show_choose_root_option_enabled():
            return False
        return self.can_choose_root_for_user(self.request.user)

    def get_chooser_mode(self) -> ChooserMode:
        raw = self.request.GET.get("chooser_mode")
        if not raw:
            return ChooserMode.CHOOSE
        try:
            return ChooserMode(raw)
        except ValueError:
            return ChooserMode.CHOOSE

    def get_move_instance(self) -> models.Model | None:
        move_pk = self.request.GET.get("move_instance_pk")
        if not move_pk:
            return None
        return get_object_or_404(self.require_model_class(), pk=unquote(str(move_pk)))

    @cached_property
    def move_permission_tester(self):
        """Per-node tester for the snippet being moved (one queryset fetch per chooser request)."""
        return self.get_move_instance().permissions_for_user(self.request.user)

    def get_browse_queryset(self) -> models.QuerySet:
        """Unfiltered tree slice for the current browse level (before per-row permission flags)."""
        model_class = self.require_model_class()
        if self.browse_parent is not None:
            queryset = self.browse_parent.get_children()
        else:
            queryset = model_class._default_manager.filter(depth=1)
        if self.get_chooser_mode() is ChooserMode.PARENT_FOR_MOVE:
            move_instance = self.get_move_instance()
            if move_instance is not None:
                queryset = queryset.exclude(pk=move_instance.pk)
        return queryset

    def get_search_queryset(self) -> models.QuerySet:
        model_class = self.require_model_class()
        policy = model_class.permission_policy
        mode = self.get_chooser_mode()
        if mode is ChooserMode.PARENT_FOR_CREATE:
            return policy.instances_user_can_add_children_to(self.request.user)
        if mode is ChooserMode.PARENT_FOR_MOVE:
            if self.get_move_instance() is None:
                raise Http404
            return policy.instances_user_can_move_to(
                self.request.user, self.get_move_instance()
            )
        return model_class._default_manager.all()

    def get_object_list(self):
        if self.filter_form.is_searching:
            return self.get_search_queryset()
        return self.get_browse_queryset()

    def apply_object_list_ordering(self, objects):
        return objects.order_by("path")

    def user_can_choose(self, obj: models.Model) -> bool:
        """Per-row choosability (mirrors ``wagtail.admin.views.chooser.can_choose_page``)."""
        user = self.request.user
        mode = self.get_chooser_mode()
        if mode is ChooserMode.PARENT_FOR_CREATE:
            return obj.permissions_for_user(user).can_add_child()
        if mode is ChooserMode.PARENT_FOR_MOVE:
            if self.get_move_instance() is None:
                raise Http404
            return self.move_permission_tester.can_move_to(obj)
        return True

    def _annotate_chooser_flags(
        self, instances: list[models.Model]
    ) -> list[models.Model]:
        for obj in instances:
            obj.can_choose = self.user_can_choose(obj)  # type: ignore[attr-defined]
            obj.can_descend = obj.numchild > 0  # type: ignore[attr-defined]
        return instances

    def get_results_page(self, request):
        page = super().get_results_page(request)
        page.object_list = self._annotate_chooser_flags(list(page.object_list))
        return page

    @property
    def is_browse_mode(self) -> bool:
        return not self.filter_form.is_searching

    @property
    def columns(self) -> list[Column]:
        if not self.is_browse_mode:
            return super().columns
        return [
            BrowseTitleColumn(
                "title",
                label=_("Title"),
                accessor=admin_display_title,
                chooser_view=self,
            ),
            NavigateColumn(
                "navigate",
                label="",
                width="10%",
                chooser_view=self,
            ),
        ]

    def get_browse_results_url(self, *, parent_pk: int | str | None = None) -> str:
        params: dict[str, str] = {}
        for param in PRESERVED_CHOOSER_PARAMS:
            value = self.request.GET.get(param)
            if value is not None:
                params[param] = value
        if parent_pk is not None:
            if not self.choose_explore_results_url_name:
                raise ImproperlyConfigured(
                    f"{self.__class__.__name__} is missing choose_explore_results_url_name."
                )
            base = reverse(
                self.choose_explore_results_url_name, args=[quote(parent_pk)]
            )
        else:
            base = reverse(self.results_url_name)
        if params:
            return f"{base}?{urlencode(params)}"
        return base

    def get_preserved_get_params(self) -> dict[str, str]:
        return {
            param: self.request.GET[param]
            for param in PRESERVED_CHOOSER_PARAMS
            if param in self.request.GET
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["preserved_get_params"] = self.get_preserved_get_params()
        browse_ancestors = (
            list(self.browse_parent.get_ancestors())
            if self.browse_parent is not None
            else []
        )
        context.update(
            {
                "is_browse_mode": self.is_browse_mode,
                "browse_parent": self.browse_parent,
                "browse_parent_title": (
                    admin_display_title(self.browse_parent)
                    if self.browse_parent is not None
                    else ""
                ),
                "browse_ancestors": browse_ancestors,
                "browse_ancestor_links": [
                    {
                        "label": admin_display_title(node),
                        "url": self.get_browse_results_url(parent_pk=node.pk),
                        "pk": node.pk,
                    }
                    for node in browse_ancestors
                ],
                "browse_results_url": self.get_browse_results_url(),
                "can_choose_root": self.can_choose_root,
                "chooser_mode": self.get_chooser_mode(),
            }
        )
        if self.is_browse_mode:
            rows = list(self.results.object_list)
            if self.browse_parent is not None:
                parent = self.browse_parent
                parent.can_choose = self.user_can_choose(parent)  # type: ignore[attr-defined]
                parent.can_descend = False  # type: ignore[attr-defined]
                rows = [parent, *rows]
            context["table"] = Table(self.columns, rows)
        return context


class BrowseTitleColumn(Column):
    cell_template_name = "wagtail_treebeard/chooser/cells/title_cell.html"

    def __init__(self, *args, chooser_view: ChooseResultsMixin, **kwargs: Any) -> None:
        self.chooser_view = chooser_view
        super().__init__(*args, **kwargs)

    def get_cell_context_data(self, instance, parent_context):
        context = super().get_cell_context_data(instance, parent_context)
        if getattr(instance, "can_choose", False):
            context["choose_url"] = self.chooser_view.append_preserved_url_parameters(
                reverse(
                    self.chooser_view.chosen_url_name,
                    args=(quote(instance.pk),),
                )
            )
        return context


class NavigateColumn(Column):
    cell_template_name = "wagtail_treebeard/chooser/cells/navigate_cell.html"

    def __init__(self, *args, chooser_view: ChooseResultsMixin, **kwargs: Any) -> None:
        self.chooser_view = chooser_view
        super().__init__(*args, **kwargs)

    def get_cell_context_data(self, instance, parent_context):
        context = super().get_cell_context_data(instance, parent_context)
        if getattr(instance, "can_descend", False):
            context["navigate_url"] = self.chooser_view.get_browse_results_url(
                parent_pk=instance.pk
            )
        return context


class ChooseView(
    ChooseResultsMixin, ChooseViewMixin, CreationFormMixin, BaseSnippetChooseView
):
    template_name = "wagtail_treebeard/chooser/chooser.html"
    preserve_url_parameters = list(PRESERVED_CHOOSER_PARAMS)

    def get_preserved_get_params(self) -> dict[str, str]:
        return {
            param: self.request.GET[param]
            for param in PRESERVED_CHOOSER_PARAMS
            if param in self.request.GET
        }

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["preserved_get_params"] = self.get_preserved_get_params()
        return context


class ChooseResultsView(
    ChooseResultsMixin, ChooseResultsViewMixin, BaseSnippetChooseView
):
    pass
