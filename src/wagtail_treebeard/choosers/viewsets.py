"""Tree-aware snippet chooser (hierarchical browse + optional search)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.models import AbstractBaseUser
from django.urls import path
from wagtail.snippets.views.chooser import (
    SnippetChooserViewSet,
    SnippetChosenMultipleView,
    SnippetChosenView,
)

from .constants import PRESERVED_CHOOSER_PARAMS
from .views import ChooseResultsView, ChooseView, ChooserCreateView
from .widgets import TreebeardModelChooser


class ChooserViewSet(SnippetChooserViewSet):
    choose_view_class = ChooseView
    choose_results_view_class = ChooseResultsView
    create_view_class = ChooserCreateView
    chosen_view_class = SnippetChosenView
    chosen_multiple_view_class = SnippetChosenMultipleView
    preserve_url_parameters = list(PRESERVED_CHOOSER_PARAMS)

    def get_common_view_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        return {
            **super().get_common_view_kwargs(ordering=["path"], **kwargs),
            "choose_explore_results_url_name": self.get_url_name(
                "choose_explore_results"
            ),
            "create_child_url_name": self.get_url_name("create_child"),
            "choose_url_name": self.get_url_name("choose"),
        }

    def get_urlpatterns(self):
        conv = self.model.snippet_viewset.pk_path_converter
        return super().get_urlpatterns() + [
            path(
                f"explore/<{conv}:parent_pk>/results/",
                self.choose_results_view,
                name="choose_explore_results",
            ),
            path(
                f"create/<{conv}:parent_pk>/",
                self.create_view,
                name="create_child",
            ),
        ]

    def can_choose_root_for_user(self, user: AbstractBaseUser) -> bool:
        return self.model.permission_policy.user_can_add_root(user)

    @property
    def choose_view(self):
        view_class = self.inject_view_methods(
            self.choose_view_class,
            ["get_object_list", "can_choose_root_for_user"],
        )
        return self.construct_view(
            view_class,
            icon=self.icon,
            page_title=self.page_title,
            search_tab_label=self.search_tab_label,
            creation_tab_label=self.creation_tab_label,
        )

    @property
    def choose_results_view(self):
        view_class = self.inject_view_methods(
            self.choose_results_view_class,
            ["get_object_list", "can_choose_root_for_user"],
        )
        return self.construct_view(view_class)

    @property
    def widget_class(self):
        return TreebeardModelChooser(model=self.model, icon=self.icon)
