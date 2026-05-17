from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect
from django.utils.functional import classproperty
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from wagtail.snippets.bulk_actions.delete import DeleteBulkAction
from wagtail.snippets.models import get_snippet_models

from wagtail_treebeard.models import TreebeardMixin


class TreebeardDeleteBulkAction(DeleteBulkAction):
    """
    Bulk delete for tree snippets: only leaf nodes (``numchild == 0``) are removed.

    Nodes with children are listed on the confirmation screen and reported via a
    warning message after any deletions complete.
    """

    template_name = "wagtail_treebeard/bulk_actions/confirm_bulk_delete.html"

    @classproperty
    def models(cls):
        return [
            model
            for model in get_snippet_models()
            if issubclass(model, TreebeardMixin) and not model._meta.abstract
        ]

    def get_actionable_objects(self):
        objects = []
        items_with_no_access = []
        items_with_children = []
        object_ids = self.request.GET.getlist("id")
        if "all" in object_ids:
            object_ids = self.get_all_objects_in_listing_query(
                self.request.GET.get("childOf")
            )

        for obj in self.get_queryset(self.model, object_ids):
            if not self.check_perm(obj):
                items_with_no_access.append(obj)
            elif obj.numchild > 0:
                items_with_children.append(obj)
            else:
                objects.append(obj)
        return objects, {
            "items_with_no_access": items_with_no_access,
            "items_with_children": items_with_children,
        }

    @classmethod
    def execute_action(cls, objects, user=None, **kwargs):
        deletable = [obj for obj in objects if obj.numchild == 0]
        return super().execute_action(deletable, user=user, **kwargs)

    def get_skipped_children_message(self, items: list) -> str:
        count = len(items)
        return ngettext(
            "Skipped deleting %(count)d item because it has child nodes.",
            "Skipped deleting %(count)d items because they have child nodes.",
            count,
        ) % {"count": count}

    def form_valid(self, form):
        objects, extra = self.get_actionable_objects()
        items_with_children = extra.get("items_with_children", [])
        if not objects:
            if items_with_children:
                messages.warning(
                    self.request,
                    self.get_skipped_children_message(items_with_children),
                )
            return redirect(self.next_url)
        response = super().form_valid(form)
        if items_with_children:
            messages.warning(
                self.request,
                self.get_skipped_children_message(items_with_children),
            )
        return response
