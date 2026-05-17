"""
Wagtail snippet admin helpers for django-treebeard MP_Node (materialised-path) models.

Stock snippets are flat CRUD; :class:`WagtailTreebeardSnippetViewSet` adds parent-picked create, move, child
reordering (using Wagtail 7+ snippet reorder / ``w-orderable`` support, omitted when ``MP_Node.node_order_by`` is
set), and safe delete UX. Wagtail 6.x and earlier are not supported. Snippet bulk delete is disabled (no bulk-actions column, no bulk-actions
footer template).

Models must inherit :class:`~wagtail_treebeard.models.TreebeardMixin` (with ``MP_Node``).
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.forms.models import modelform_factory
from django.urls import path
from treebeard.mp_tree import MP_Node
from wagtail.snippets.views import snippets as snippet_views

from wagtail_treebeard.choosers import ChooserViewSet
from wagtail_treebeard.forms import WagtailTreebeardAdminModelForm
from wagtail_treebeard.models import TreebeardMixin
from wagtail_treebeard.utils import (
    get_breadcrumb_ancestor_queryset,
    model_supports_manual_ordering,
)
from wagtail_treebeard.views import (
    ConfirmAddPositionView,
    CreateView,
    DeleteView,
    EditView,
    IndexView,
    MoveView,
    ReorderChildrenView,
    ReorderChildRowView,
    ReorderRootEntriesView,
    ReorderRootEntryRowView,
)


class WagtailTreebeardSnippetViewSet(snippet_views.SnippetViewSet):
    """
    Snippet admin for :class:`~wagtail_treebeard.models.TreebeardMixin` models:
    parent-aware create URLs, per-row move/add-child, child reordering, and delete blocked when
    ``numchild > 0``.
    """

    model: type[TreebeardMixin]

    index_view_class = IndexView
    edit_view_class = EditView
    delete_view_class = DeleteView
    add_view_class = CreateView
    reorder_children_view_class: type[ReorderChildrenView] = ReorderChildrenView
    reorder_child_row_view_class: type[ReorderChildRowView] = ReorderChildRowView
    reorder_root_entries_view_class: type[ReorderRootEntriesView] = (
        ReorderRootEntriesView
    )
    reorder_root_entry_row_view_class: type[ReorderRootEntryRowView] = (
        ReorderRootEntryRowView
    )

    chooser_viewset_class = ChooserViewSet
    chooser_per_page = 50

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not issubclass(self.model, TreebeardMixin) or not issubclass(
            self.model, MP_Node
        ):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__}.model must inherit TreebeardMixin and MP_Node (got {self.model!r})."
            )

    @property
    def permission_policy(self):
        return self.model.permission_policy

    @classmethod
    def get_breadcrumb_ancestors(cls, node: models.Model):
        """
        Ancestors for breadcrumb UI, optionally narrowed via :attr:`~wagtail_treebeard.models.TreebeardMixin.breadcrumb_title_fields`.

        Same ordering as :meth:`~treebeard.mp_tree.MP_Node.get_ancestors`.
        """
        return get_breadcrumb_ancestor_queryset(node)

    def get_exclude_form_fields(self):
        exclude = list(super().get_exclude_form_fields() or [])
        for field_name in ("path", "depth", "numchild"):
            if field_name not in exclude:
                exclude.append(field_name)
        return exclude

    def get_form_class(self, *, for_update=False):
        if self._edit_handler:
            return self._edit_handler.get_form_class()
        fields = self.get_form_fields()
        exclude = self.get_exclude_form_fields()
        if fields is None and exclude is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must specify form_fields or exclude_form_fields."
            )
        return modelform_factory(
            self.model,
            form=WagtailTreebeardAdminModelForm,
            formfield_callback=self.formfield_for_dbfield,
            fields=fields,
            exclude=exclude,
        )

    def get_common_view_kwargs(self, **kwargs: Any) -> dict[str, Any]:
        common: dict[str, Any] = {
            **super().get_common_view_kwargs(**kwargs),
            "permission_policy": self.permission_policy,
            "add_root_url_name": self.get_url_name("add_root"),
            "add_child_url_name": self.get_url_name("add_child"),
            "move_url_name": self.get_url_name("move"),
            "index_explore_url_name": self.get_url_name("explore"),
            "index_explore_results_url_name": self.get_url_name("explore_results"),
        }
        if model_supports_manual_ordering(self.model):
            common["reorder_children_url_name"] = self.get_url_name("reorder_children")
            common["reorder_children_row_url_name"] = self.get_url_name(
                "reorder_children_row"
            )
            common["reorder_root_entries_url_name"] = self.get_url_name(
                "reorder_root_entries"
            )
            common["reorder_root_entry_row_url_name"] = self.get_url_name(
                "reorder_root_entry_row"
            )
        else:
            common["reorder_children_url_name"] = None
            common["reorder_children_row_url_name"] = None
            common["reorder_root_entries_url_name"] = None
            common["reorder_root_entry_row_url_name"] = None
        return common

    def get_index_template(self) -> list[str]:
        """Prefer a snippet index variant without the bulk-actions footer (see ``wagtail_treebeard/index.html``)."""
        return [
            "wagtail_treebeard/index.html",
            *super().get_index_template(),
        ]

    def get_index_results_template(self) -> list[str]:
        return [
            "wagtail_treebeard/index_results.html",
            *super().get_index_results_template(),
        ]

    @property
    def add_view(self):
        return self.construct_view(self.add_view_class, **self.get_add_view_kwargs())

    @property
    def confirm_add_position_view(self):
        return self.construct_view(
            ConfirmAddPositionView,
            model=self.model,
            index_url_name=self.get_url_name("list"),
            breadcrumbs_items=self.breadcrumbs_items,
            add_root_url_name=self.get_url_name("add_root"),
            add_child_url_name=self.get_url_name("add_child"),
        )

    @property
    def move_view(self):
        return self.construct_view(MoveView)

    @property
    def reorder_children_view(self):
        return self.construct_view(self.reorder_children_view_class)

    @property
    def reorder_child_row_view(self):
        return self.construct_view(self.reorder_child_row_view_class)

    @property
    def reorder_root_entries_view(self):
        return self.construct_view(self.reorder_root_entries_view_class)

    @property
    def reorder_root_entry_row_view(self):
        return self.construct_view(self.reorder_root_entry_row_view_class)

    def get_urlpatterns(self):
        conv = self.pk_path_converter
        patterns = list(super().get_urlpatterns())
        explore_routes = [
            path(
                f"explore/<{conv}:parent_pk>/results/",
                self.index_results_view,
                name="explore_results",
            ),
            path(
                f"explore/<{conv}:parent_pk>/",
                self.index_view,
                name="explore",
            ),
        ]
        for i, route in enumerate(patterns):
            if getattr(route, "name", None) == "list_results":
                patterns[i + 1 : i + 1] = explore_routes
                break
        else:
            patterns = explore_routes + patterns
        for i, route in enumerate(patterns):
            if getattr(route, "name", None) == "add":
                patterns[i] = path("add/", self.confirm_add_position_view, name="add")
                break
        insert_at = next(
            (i for i, r in enumerate(patterns) if getattr(r, "name", None) == "add"),
            None,
        )
        extra: list = []
        if model_supports_manual_ordering(self.model):
            extra.extend(
                [
                    path(
                        f"reorder-children/<{conv}:parent_pk>/reorder/<{conv}:pk>/",
                        self.reorder_child_row_view,
                        name="reorder_children_row",
                    ),
                    path(
                        f"reorder-children/<{conv}:parent_pk>/",
                        self.reorder_children_view,
                        name="reorder_children",
                    ),
                    path(
                        f"reorder-roots/reorder/<{conv}:pk>/",
                        self.reorder_root_entry_row_view,
                        name="reorder_root_entry_row",
                    ),
                    path(
                        "reorder-roots/",
                        self.reorder_root_entries_view,
                        name="reorder_root_entries",
                    ),
                ]
            )
        extra.extend(
            [
                path(
                    "add/root/",
                    self.add_view,
                    name="add_root",
                ),
                path(
                    f"<{conv}:parent_pk>/add_child/",
                    self.add_view,
                    name="add_child",
                ),
                path(
                    f"<{conv}:pk>/move/",
                    self.move_view,
                    name="move",
                ),
            ]
        )
        if insert_at is not None:
            patterns[insert_at + 1 : insert_at + 1] = extra
        else:
            patterns.extend(extra)
        return patterns
