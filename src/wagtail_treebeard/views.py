"""Wagtail admin views, forms, and tables for tree-shaped snippet listings and edits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import messages
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import (
    ImproperlyConfigured,
    PermissionDenied,
    ValidationError,
)
from django.db import models, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView
from wagtail.admin.ui.tables import (
    BulkActionsCheckboxColumn,
    Column,
    Table,
    TitleColumn,
)
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin
from wagtail.admin.widgets.button import Button, HeaderButton
from wagtail.log_actions import log
from wagtail.models.orderable import set_max_order
from wagtail.snippets.views import snippets as snippet_views

from wagtail_treebeard.forms import (
    ConfirmAddPositionForm,
    MoveForm,
    WagtailTreebeardAdminModelForm,
)
from wagtail_treebeard.utils import (
    INDEX_PARENT_PK_QUERY_PARAM,
    admin_display_title,
    reverse_index_explore_url,
    insert_breadcrumbs_before_last,
    move_mp_child_to_position,
    move_mp_root_to_position,
    mp_node_breadcrumb_ancestor_list,
    mp_node_breadcrumb_chain,
    mp_node_explore_breadcrumb_items,
)


if TYPE_CHECKING:
    from wagtail_treebeard.permission_policy import TreebeardPermissionPolicyMixin


class TreebeardViewMixin:
    """``model.permission_policy`` and ``model_opts`` for treebeard snippet admin views."""

    model: type[models.Model] | None = None

    def require_model(self) -> type[models.Model]:
        if self.model is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} requires a model.")
        return self.model

    @cached_property
    def permission_policy(self) -> TreebeardPermissionPolicyMixin:
        return self.require_model().permission_policy

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        if self.model is not None:
            context["model_opts"] = self.model._meta
        return context

    def get_admin_object_title(self, instance: models.Model) -> str:
        return admin_display_title(instance)


class ConfirmAddPositionView(TreebeardViewMixin, WagtailAdminTemplateMixin, FormView):
    """Step one of create: pick a parent (or root), then redirect to the real create URL."""

    template_name = "wagtail_treebeard/confirm_add_position.html"
    form_class = ConfirmAddPositionForm
    page_title = _("Confirm add position")

    add_root_url_name: str | None = None
    add_child_url_name: str | None = None
    index_url_name: str | None = None
    header_icon = "folder"
    breadcrumbs_items: list | None = None
    user_can_add_root: bool = False
    user_can_add_children: bool = False
    parent_queryset: models.QuerySet | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        if (
            self.model is None
            or self.add_root_url_name is None
            or self.add_child_url_name is None
            or self.index_url_name is None
            or self.breadcrumbs_items is None
        ):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        self.user_can_add_root = self.permission_policy.user_can_add_root(request.user)
        self.parent_queryset = (
            self.permission_policy.instances_user_can_add_children_to(request.user)
        )
        self.user_can_add_children = self.parent_queryset.exists()
        if not self.user_can_add_root and not self.user_can_add_children:
            raise PermissionDenied

    def dispatch(self, request, *args: Any, **kwargs: Any):
        if not self.user_can_add_children:
            return redirect(self.add_root_url_name)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        kwargs["model"] = self.model
        kwargs["parent_queryset"] = self.parent_queryset
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["cancel_url"] = reverse(self.index_url_name)
        context["user_can_add_root"] = self.user_can_add_root
        context["add_root_url"] = reverse(self.add_root_url_name)
        return context

    def form_valid(self, form: ConfirmAddPositionForm):
        parent = form.cleaned_data["parent"]
        return redirect(self.add_child_url_name, quote(parent.pk))

    def get_breadcrumbs_items(self) -> list[dict[str, str]]:
        return self.breadcrumbs_items + [
            {
                "url": reverse(self.index_url_name),
                "label": capfirst(self.model._meta.verbose_name_plural),
            },
            {"url": "", "label": str(self.get_page_title())},
        ]


class CreateView(TreebeardViewMixin, snippet_views.CreateView):
    """
    Create under an MP parent (``parent_pk`` in URL) or as a root (``add/root/`` with no parent).

    When creating under a parent, breadcrumbs show the full ancestor chain (each linking to explore).
    """

    parent: models.Model | None = None

    def get_form_class(self):
        form_class = getattr(self, "form_class", None)
        if form_class is not None:
            return form_class
        return self.require_model().snippet_viewset.get_form_class()

    index_explore_url_name: str | None = None

    def get_breadcrumbs_items(self) -> list[dict[str, Any]]:
        items = super().get_breadcrumbs_items()
        if self.parent is None:
            return items
        extra = mp_node_explore_breadcrumb_items(
            mp_node_breadcrumb_chain(self.parent),
            explore_url_name=self.index_explore_url_name,
        )
        return insert_breadcrumbs_before_last(items, extra)

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.parent = None
        if "parent_pk" in self.kwargs:
            self.parent = get_object_or_404(
                self.model, pk=unquote(str(self.kwargs["parent_pk"]))
            )
        if self.parent is None:
            if not self.permission_policy.user_can_add_root(request.user):
                raise PermissionDenied(_("You cannot add a root-level node."))
        elif (
            not self.permission_policy.instances_user_can_add_children_to(request.user)
            .filter(pk=self.parent.pk)
            .exists()
        ):
            raise PermissionDenied(_("You cannot add a child under this node."))

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        if issubclass(self.get_form_class(), WagtailTreebeardAdminModelForm):
            kwargs["parent"] = self.parent
        return kwargs

    def save_instance(self) -> models.Model:
        instance = self.form.save(commit=False)

        if self.parent is None:
            self.object = self.model.add_root(instance=instance)
        else:
            self.object = self.parent.add_child(instance=instance)

        self.form.save_m2m()
        if (
            self.sort_order_field
            and getattr(self.object, self.sort_order_field, None) is None
        ):
            set_max_order(self.object, self.sort_order_field)
        log(instance=self.object, action="wagtail.create", content_changed=True)
        return self.object


class EditView(TreebeardViewMixin, snippet_views.EditView):
    index_explore_url_name: str | None = None

    def get_page_subtitle(self) -> str:
        if self.object is not None:
            return self.get_admin_object_title(self.object)
        return super().get_page_subtitle()

    def get_breadcrumbs_items(self) -> list[dict[str, Any]]:
        items = super().get_breadcrumbs_items()
        if self.object is None:
            return items
        extra = mp_node_explore_breadcrumb_items(
            mp_node_breadcrumb_ancestor_list(self.object),
            explore_url_name=self.index_explore_url_name,
        )
        return insert_breadcrumbs_before_last(items, extra)


class MoveView(TreebeardViewMixin, WagtailAdminTemplateMixin, FormView):
    template_name = "wagtail_treebeard/move.html"
    form_class = MoveForm
    page_title = _("Move")

    index_url_name: str | None = None
    index_explore_url_name: str | None = None
    header_icon = "arrow-right"
    breadcrumbs_items: list | None = None
    user_can_move_to_root: bool = False
    user_can_move_to_new_parent: bool = False
    object_to_move: models.Model | None = None
    parent_queryset: models.QuerySet | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        if self.model is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        self.object_to_move = get_object_or_404(
            self.model, pk=unquote(str(self.kwargs["pk"]))
        )
        perms = self.object_to_move.permissions_for_user(request.user)
        if not perms.can_move():
            raise PermissionDenied(_("You cannot move this node."))
        policy = perms.permission_policy
        self.user_can_move_to_root = policy.user_can_add_root(request.user)
        self.parent_queryset = policy.instances_user_can_move_to(
            request.user, self.object_to_move
        )
        self.user_can_move_to_new_parent = self.parent_queryset.exists()

    def get_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_form_kwargs()
        model, object_to_move, parent_queryset, _index_url_name = (
            self._registered_move_state()
        )
        kwargs["model"] = model
        kwargs["parent_queryset"] = parent_queryset
        kwargs["move_instance_pk"] = object_to_move.pk
        return kwargs

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        _model, _object_to_move, parent_queryset, index_url_name = (
            self._registered_move_state()
        )
        context["cancel_url"] = reverse(index_url_name)
        context["user_can_move_to_new_parent"] = self.user_can_move_to_new_parent
        context["show_move_to_root"] = (
            self.user_can_move_to_root and self.object_to_move.depth > 1
        )
        return context

    def post(self, request, *args: Any, **kwargs: Any):
        if request.POST.get("move_to_root"):
            if not self.user_can_move_to_root:
                raise PermissionDenied
            return self.form_valid_move_to_root()
        return super().post(request, *args, **kwargs)

    def _registered_move_state(
        self,
    ) -> tuple[type[models.Model], models.Model, models.QuerySet, str]:
        if self.object_to_move is None or self.parent_queryset is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        if self.index_url_name is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing index_url_name."
            )
        return (
            self.require_model(),
            self.object_to_move,
            self.parent_queryset,
            self.index_url_name,
        )

    def form_valid_move_to_root(self):
        model, object_to_move, _parent_queryset, index_url_name = (
            self._registered_move_state()
        )
        if object_to_move.depth <= 1:
            messages.error(self.request, _("This node is already at the root level."))
            return redirect(self.request.path)
        roots = model.get_root_nodes()
        if not roots.exists():
            messages.error(self.request, _("There is no root node to move beside."))
            return redirect(self.request.path)
        try:
            with transaction.atomic():
                object_to_move.move(roots.first(), pos="left")
        except ValidationError as exc:
            for error in exc.error_list:
                messages.error(self.request, error.message)
            return redirect(self.request.path)
        messages.success(
            self.request,
            _("Moved '%(title)s' to the root level.")
            % {"title": admin_display_title(object_to_move)},
        )
        return redirect(reverse(index_url_name))

    def form_valid(self, form: MoveForm):
        _model, object_to_move, parent_queryset, index_url_name = (
            self._registered_move_state()
        )
        new_parent = form.cleaned_data["new_parent"]
        if not parent_queryset.filter(pk=new_parent.pk).exists():
            messages.error(self.request, _("That parent is not a valid move target."))
            return redirect(self.request.path)
        try:
            with transaction.atomic():
                object_to_move.move(new_parent, pos="last-child")
        except ValidationError as exc:
            for error in exc.error_list:
                messages.error(self.request, error.message)
            return redirect(self.request.path)
        messages.success(
            self.request,
            _("Moved '%(title)s' under '%(parent)s'.")
            % {
                "title": admin_display_title(object_to_move),
                "parent": admin_display_title(new_parent),
            },
        )
        return redirect(reverse(index_url_name))

    def get_breadcrumbs_items(self) -> list[dict[str, str]]:
        model, object_to_move, _parent_queryset, index_url_name = (
            self._registered_move_state()
        )
        items: list[dict[str, str]] = list(self.breadcrumbs_items)
        items.append(
            {
                "url": reverse(index_url_name),
                "label": capfirst(model._meta.verbose_name_plural),
            }
        )
        items.extend(
            mp_node_explore_breadcrumb_items(
                mp_node_breadcrumb_chain(object_to_move),
                explore_url_name=self.index_explore_url_name,
            )
        )
        items.append({"url": "", "label": str(self.get_page_title())})
        return items


class ReorderChildrenView(TreebeardViewMixin, WagtailAdminTemplateMixin, TemplateView):
    """
    Full listing of a node's direct children with drag-and-drop reordering.

    Uses the same ``w-orderable`` Stimulus contract as snippet index reordering; POST requests
    go to :class:`ReorderChildRowView` which applies sibling order via treebeard ``move``.
    """

    template_name = "wagtail_treebeard/reorder_children.html"
    page_title = _("Reorder children")

    reorder_children_row_url_name: str | None = None
    index_url_name: str | None = None
    index_explore_url_name: str | None = None
    header_icon = "list-ul"
    breadcrumbs_items: list | None = None
    parent: models.Model | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        model = self.require_model()
        self.parent = get_object_or_404(model, pk=unquote(str(kwargs["parent_pk"])))

    def get(self, request, *args: Any, **kwargs: Any):
        parent = self.parent
        if parent is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        policy = self.permission_policy
        perms = parent.permissions_for_user(request.user)
        if not policy.user_has_permission_for_instance(request.user, "change", parent):
            raise PermissionDenied
        if parent.numchild < 2:
            if parent.numchild == 0:
                message = _("This item has no child nodes to reorder.")
            else:
                message = _("There are not enough child nodes to reorder.")
            messages.error(request, message)
            if self.index_explore_url_name is None:
                raise ImproperlyConfigured(
                    f"{self.__class__.__name__} is missing index_explore_url_name."
                )
            return redirect(
                reverse_index_explore_url(self.index_explore_url_name, parent.pk)
            )
        if not perms.can_reorder_children():
            raise PermissionDenied
        return super().get(request, *args, **kwargs)

    def get_page_subtitle(self) -> str:
        if self.parent is not None:
            return admin_display_title(self.parent)
        return ""

    def _registered_reorder_state(
        self,
    ) -> tuple[models.Model, type[models.Model], str, str]:
        parent = self.parent
        if parent is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        if (
            self.index_explore_url_name is None
            or self.reorder_children_row_url_name is None
        ):
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing index or reorder URL names."
            )
        return (
            parent,
            self.require_model(),
            self.index_explore_url_name,
            self.reorder_children_row_url_name,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        parent, _model, index_explore_url_name, reorder_children_row_url_name = (
            self._registered_reorder_state()
        )
        children = list(
            self.permission_policy.changeable_siblings_queryset(
                self.request.user, parent=parent
            )
        )
        context["parent"] = parent
        context["cancel_url"] = reverse_index_explore_url(
            index_explore_url_name, parent.pk
        )
        context["children_rows"] = [
            {"pk_quoted": quote(c.pk), "label": admin_display_title(c)}
            for c in children
        ]
        context["child_count"] = len(children)
        context["reorder_url"] = reverse(
            reorder_children_row_url_name,
            args=[quote(parent.pk), 999999],
        )
        return context

    def get_breadcrumbs_items(self) -> list[dict[str, str]]:
        parent, model, index_explore_url_name, _reorder_children_row_url_name = (
            self._registered_reorder_state()
        )
        items: list[dict[str, str]] = list(self.breadcrumbs_items)
        if self.index_url_name is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing index_url_name."
            )
        items.append(
            {
                "url": reverse(self.index_url_name),
                "label": capfirst(model._meta.verbose_name_plural),
            }
        )
        items.extend(
            mp_node_explore_breadcrumb_items(
                mp_node_breadcrumb_chain(parent),
                explore_url_name=index_explore_url_name,
            )
        )
        items.append({"url": "", "label": str(self.get_page_title())})
        return items


class ReorderChildRowView(TreebeardViewMixin, View):
    """AJAX handler: one child row moved to a new index (``?position=``), matching snippet reorder."""

    index_url_name: str | None = None
    http_method_names = ["post", "head", "options"]

    def post(self, request, *args: Any, **kwargs: Any):
        parent_pk = str(kwargs["parent_pk"])
        pk = str(kwargs["pk"])
        model = self.model
        if model is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} requires a model.")
        parent = get_object_or_404(model, pk=unquote(parent_pk))
        item = get_object_or_404(model, pk=unquote(pk))

        policy = self.permission_policy
        if not policy.user_can_reorder_siblings_at_level(request.user, parent=parent):
            raise PermissionDenied

        item_parent = item.get_parent()
        if item_parent is None or item_parent.pk != parent.pk:
            return JsonResponse(
                {"success": False, "error": "invalid_child"}, status=400
            )

        siblings = list(
            policy.changeable_siblings_queryset(request.user, parent=parent)
        )
        pks = [s.pk for s in siblings]
        try:
            current_position = pks.index(item.pk)
        except ValueError:
            return JsonResponse({"success": False}, status=404)

        try:
            new_position = int(request.GET.get("position", ""))
        except ValueError:
            new_position = -1
        if new_position < 0 or new_position >= len(pks):
            new_position = len(pks) - 1

        if new_position == current_position:
            return JsonResponse({"success": True})

        try:
            move_mp_child_to_position(parent, item, new_position, siblings=siblings)
        except ValidationError as exc:
            msg = exc.error_list[0].message if exc.error_list else str(exc)
            return JsonResponse({"success": False, "error": msg}, status=400)

        log(instance=parent, action="wagtail.edit", content_changed=True)
        return JsonResponse({"success": True})


class ReorderRootEntriesView(
    TreebeardViewMixin, WagtailAdminTemplateMixin, TemplateView
):
    """
    Full listing of root-level entries with drag-and-drop reordering.

    Uses the same ``w-orderable`` Stimulus contract as :class:`ReorderChildrenView`; POST requests
    go to :class:`ReorderRootEntryRowView`.
    """

    template_name = "wagtail_treebeard/reorder_root_entries.html"
    page_title = _("Reorder root entries")

    reorder_root_entry_row_url_name: str | None = None
    index_url_name: str | None = None
    header_icon = "list-ul"
    breadcrumbs_items: list | None = None

    def get(self, request, *args: Any, **kwargs: Any):
        policy = self.permission_policy
        if self.index_url_name is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing index_url_name."
            )
        index_url = reverse(self.index_url_name)
        if not policy.user_has_permission(request.user, "change"):
            raise PermissionDenied
        if not policy.user_can_reorder_roots(request.user):
            messages.error(request, _("There are not enough root entries to reorder."))
            return redirect(index_url)
        return super().get(request, *args, **kwargs)

    def _registered_reorder_state(self) -> tuple[type[models.Model], str, str]:
        if self.index_url_name is None or self.reorder_root_entry_row_url_name is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing index or reorder URL names."
            )
        return (
            self.require_model(),
            self.index_url_name,
            self.reorder_root_entry_row_url_name,
        )

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        model, index_url_name, reorder_root_entry_row_url_name = (
            self._registered_reorder_state()
        )
        roots = list(
            self.permission_policy.changeable_siblings_queryset(self.request.user)
        )
        context["cancel_url"] = reverse(index_url_name)
        context["entry_rows"] = [
            {"pk_quoted": quote(root.pk), "label": admin_display_title(root)}
            for root in roots
        ]
        context["entry_count"] = len(roots)
        context["reorder_url"] = reverse(
            reorder_root_entry_row_url_name,
            args=[999999],
        )
        return context

    def get_breadcrumbs_items(self) -> list[dict[str, str]]:
        model, index_url_name, _reorder_root_entry_row_url_name = (
            self._registered_reorder_state()
        )
        items: list[dict[str, str]] = list(self.breadcrumbs_items)
        items.append(
            {
                "url": reverse(index_url_name),
                "label": capfirst(model._meta.verbose_name_plural),
            }
        )
        items.append({"url": "", "label": str(self.get_page_title())})
        return items


class ReorderRootEntryRowView(TreebeardViewMixin, View):
    """AJAX handler: one root row moved to a new index (``?position=``)."""

    index_url_name: str | None = None
    http_method_names = ["post", "head", "options"]

    def post(self, request, *args: Any, **kwargs: Any):
        pk = str(kwargs["pk"])
        model = self.model
        if model is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} requires a model.")
        item = get_object_or_404(model, pk=unquote(pk))

        if item.depth != 1:
            return JsonResponse({"success": False, "error": "invalid_root"}, status=400)

        policy = self.permission_policy
        if not policy.user_can_reorder_roots(request.user):
            raise PermissionDenied
        siblings = list(policy.changeable_siblings_queryset(request.user))
        pks = [s.pk for s in siblings]
        try:
            current_position = pks.index(item.pk)
        except ValueError:
            return JsonResponse({"success": False}, status=404)

        try:
            new_position = int(request.GET.get("position", ""))
        except ValueError:
            new_position = -1
        if new_position < 0 or new_position >= len(pks):
            new_position = len(pks) - 1

        if new_position == current_position:
            return JsonResponse({"success": True})

        try:
            move_mp_root_to_position(item, new_position, siblings=siblings)
        except ValidationError as exc:
            msg = exc.error_list[0].message if exc.error_list else str(exc)
            return JsonResponse({"success": False, "error": msg}, status=400)

        log(instance=item, action="wagtail.edit", content_changed=True)
        return JsonResponse({"success": True})


class DeleteView(TreebeardViewMixin, snippet_views.DeleteView):
    def get_page_subtitle(self) -> str:
        return self.get_admin_object_title(self.object)

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.require_model()
        if self.object.numchild > 0:
            raise PermissionDenied(
                _("Delete is not available while this item has child nodes.")
            )


class WagtailTreebeardTable(Table):
    """
    Indent the title column from treebeard ``MP_Node.depth`` when showing a flat/search listing.

    Explorer browse mode uses a plain :class:`~wagtail.admin.ui.tables.Table` instead (one level at a time).
    """

    def __init__(self, *args: Any, tree_indent: bool = True, **kwargs: Any) -> None:
        self.tree_indent = tree_indent
        super().__init__(*args, **kwargs)

    def get_row_attrs(self, instance: models.Model) -> dict[str, str | bool]:
        attrs = super().get_row_attrs(instance)
        if not self.tree_indent:
            return attrs
        depth = getattr(instance, "depth", None)
        try:
            depth_int = int(depth)
        except (TypeError, ValueError):
            return attrs
        if depth_int < 1:
            return attrs
        indent_rem = round((depth_int - 1) * 1.25, 3)
        fragment = f"--tree-indent: {indent_rem}rem;"
        existing = attrs.get("style", "")
        if isinstance(existing, str) and existing.strip():
            attrs["style"] = f"{existing.strip()}; {fragment}"
        else:
            attrs["style"] = fragment
        return attrs


class WagtailTreebeardExploreNavigateColumn(Column):
    """Open a node's children in the snippet index (page explorer ``NavigateToChildrenColumn`` pattern)."""

    cell_template_name = "wagtail_treebeard/cells/explore_navigate_cell.html"

    def __init__(
        self,
        *args: Any,
        add_child_url_name: str | None = None,
        index_explore_url_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.add_child_url_name = add_child_url_name
        self.index_explore_url_name = index_explore_url_name

    def get_cell_context_data(self, instance, parent_context):
        context = super().get_cell_context_data(instance, parent_context)
        request = parent_context["request"]
        perms = instance.permissions_for_user(request.user)
        context["node_perms"] = perms
        context["admin_title"] = admin_display_title(instance)
        if instance.numchild > 0 and self.index_explore_url_name:
            context["explore_url"] = reverse_index_explore_url(
                self.index_explore_url_name, instance.pk
            )
        if self.add_child_url_name and perms.can_add_child():
            context["add_child_url"] = reverse(
                self.add_child_url_name, args=[quote(instance.pk)]
            )
        return context


class TreebeardIndexBrowseMixin:
    """
    Explorer-style snippet index: list direct children of a parent (roots at ``list``).

    Browse uses ``explore/<parent_pk>/`` URLs; search/filter may scope to the current subtree.
    """

    browse_parent: models.Model | None = None
    index_explore_url_name: str | None = None
    index_explore_results_url_name: str | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.browse_parent = None
        parent_pk = kwargs.get("parent_pk")
        if parent_pk and self.model is not None:
            self.browse_parent = get_object_or_404(
                self.model, pk=unquote(str(parent_pk))
            )

    def dispatch(self, request, *args: Any, **kwargs: Any):
        legacy_pk = request.GET.get(INDEX_PARENT_PK_QUERY_PARAM)
        if legacy_pk and "parent_pk" not in kwargs and self.index_explore_url_name:
            return redirect(
                reverse_index_explore_url(
                    self.index_explore_url_name, unquote(str(legacy_pk))
                )
            )
        return super().dispatch(request, *args, **kwargs)

    @cached_property
    def is_browse_mode(self) -> bool:
        return not self.is_searching and not self.is_filtering

    def get_base_queryset(self):
        model = self.model
        if model is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} requires a model for queryset access."
            )
        if self.is_browse_mode:
            if self.browse_parent is not None:
                return self.browse_parent.get_children().order_by("path")
            return model._default_manager.filter(depth=1).order_by("path")
        queryset = super().get_base_queryset()
        if self.browse_parent is not None:
            queryset = queryset.filter(path__startswith=self.browse_parent.path)
        return queryset

    def get_index_results_url(self):
        if self.browse_parent is not None and self.index_explore_results_url_name:
            return reverse(
                self.index_explore_results_url_name,
                args=[quote(self.browse_parent.pk)],
            )
        return super().get_index_results_url()

    def get_index_url(self):
        if self.browse_parent is not None and self.index_explore_url_name:
            return reverse_index_explore_url(
                self.index_explore_url_name, self.browse_parent.pk
            )
        return super().get_index_url()

    def get_page_subtitle(self) -> str:
        # Current node is the final breadcrumb label when drilling in (not a subtitle).
        if self.is_browse_mode and self.browse_parent is not None:
            return ""
        return super().get_page_subtitle()

    def get_breadcrumbs_items(self) -> list[dict[str, Any]]:
        items = super().get_breadcrumbs_items()
        if (
            not self.is_browse_mode
            or self.browse_parent is None
            or self.model is None
            or self.index_explore_url_name is None
            or self.index_url_name is None
        ):
            return items
        index_label = capfirst(self.model._meta.verbose_name_plural)
        if items and not items[-1].get("url"):
            index_label = items[-1].get("label", index_label)
            items = items[:-1]
        items.extend(
            [
                {
                    "url": reverse(self.index_url_name),
                    "label": index_label,
                },
                *[
                    {
                        "url": reverse_index_explore_url(
                            self.index_explore_url_name, node.pk
                        ),
                        "label": admin_display_title(node),
                    }
                    for node in mp_node_breadcrumb_ancestor_list(self.browse_parent)
                ],
                {
                    "url": "",
                    "label": admin_display_title(self.browse_parent),
                },
            ]
        )
        return items

    def get_table_kwargs(self):
        kwargs = super().get_table_kwargs()
        if self.is_browse_mode:
            kwargs.pop("tree_indent", None)
        else:
            kwargs["tree_indent"] = True
        return kwargs

    def get_context_data(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(*args, **kwargs)
        if self.index_url_name:
            browse_index_url = reverse(self.index_url_name)
        else:
            browse_index_url = self.get_index_url()
        browse_ancestors = (
            mp_node_breadcrumb_ancestor_list(self.browse_parent)
            if self.browse_parent is not None
            else []
        )
        context.update(
            {
                "is_browse_mode": self.is_browse_mode,
                "show_bulk_actions": not self.is_browse_mode,
                "browse_parent": self.browse_parent,
                "browse_ancestor_links": [
                    {
                        "label": admin_display_title(node),
                        "url": reverse_index_explore_url(
                            self.index_explore_url_name, node.pk
                        ),
                        "pk": node.pk,
                    }
                    for node in browse_ancestors
                ]
                if self.index_explore_url_name
                else [],
                "browse_index_url": browse_index_url,
                "add_child_url_name": self.add_child_url_name,
            }
        )
        if (
            self.is_browse_mode
            and self.browse_parent is not None
            and self.add_child_url_name
            and self.browse_parent.permissions_for_user(
                self.request.user
            ).can_add_child()
        ):
            context["add_url"] = reverse(
                self.add_child_url_name, args=[quote(self.browse_parent.pk)]
            )
        return context


class IndexView(TreebeardIndexBrowseMixin, TreebeardViewMixin, snippet_views.IndexView):
    add_child_url_name: str | None = None
    move_url_name: str | None = None
    reorder_children_url_name: str | None = None
    reorder_root_entries_url_name: str | None = None

    def _treebeard_title_column(self) -> TitleColumn:
        column_class = self._get_title_column_class(TitleColumn)
        return column_class(
            "title",
            label=_("Title"),
            accessor=admin_display_title,
            get_url=lambda instance: self.get_edit_url(instance)
            or self.get_inspect_url(instance),
            get_title_id=lambda instance: f"snippet_{quote(instance.pk)}_title",
        )

    @cached_property
    def list_display(self):
        from wagtail.admin.ui.tables import UpdatedAtColumn

        return [self._treebeard_title_column(), UpdatedAtColumn()]

    @cached_property
    def header_buttons(self):
        if not self.is_browse_mode:
            return super().header_buttons

        buttons: list[HeaderButton] = []
        if (
            self.browse_parent is None
            and self.reorder_root_entries_url_name
            and self.permission_policy.user_can_reorder_roots(self.request.user)
        ):
            buttons.append(
                HeaderButton(
                    _("Reorder root entries"),
                    url=reverse(self.reorder_root_entries_url_name),
                    icon_name="list-ul",
                )
            )
        elif self.browse_parent is not None:
            perms = self.browse_parent.permissions_for_user(self.request.user)
            if self.reorder_children_url_name and perms.can_reorder_children():
                buttons.append(
                    HeaderButton(
                        _("Reorder children"),
                        url=reverse(
                            self.reorder_children_url_name,
                            args=[quote(self.browse_parent.pk)],
                        ),
                        icon_name="list-ul",
                    )
                )
            if self.add_child_url_name and perms.can_add_child():
                buttons.append(
                    HeaderButton(
                        _("Add child"),
                        url=reverse(
                            self.add_child_url_name, args=[quote(self.browse_parent.pk)]
                        ),
                        icon_name="plus",
                    )
                )
        if buttons:
            return buttons
        return super().header_buttons

    @cached_property
    def table_class(self):
        """Use a plain table in browse mode; indent rows in flat search listings."""
        if self.is_browse_mode:
            return Table
        return WagtailTreebeardTable

    @cached_property
    def columns(self):
        if self.is_browse_mode:
            return [
                self._treebeard_title_column(),
                WagtailTreebeardExploreNavigateColumn(
                    "navigate",
                    label="",
                    width="10%",
                    add_child_url_name=self.add_child_url_name,
                    index_explore_url_name=self.index_explore_url_name,
                ),
            ]
        return [
            BulkActionsCheckboxColumn("bulk_actions", obj_type="snippet"),
            *super(snippet_views.IndexView, self).columns[1:],
        ]

    def get_list_more_buttons(self, instance: models.Model) -> list:
        buttons = super().get_list_more_buttons(instance)
        if self.add_child_url_name is None or self.move_url_name is None:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} must be registered via WagtailTreebeardSnippetViewSet."
            )
        delete_url = self.get_delete_url(instance)
        if delete_url and instance.numchild > 0:
            buttons = [b for b in buttons if getattr(b, "url", None) != delete_url]

        perms = instance.permissions_for_user(self.request.user)
        if perms.can_add_child():
            buttons.append(
                Button(
                    label=_("Add child"),
                    url=reverse(self.add_child_url_name, args=[quote(instance.pk)]),
                    icon_name="plus",
                    priority=40,
                )
            )
        if perms.can_move():
            buttons.append(
                Button(
                    label=_("Move"),
                    url=reverse(self.move_url_name, args=[quote(instance.pk)]),
                    icon_name="arrow-right",
                    priority=41,
                )
            )
        if self.reorder_children_url_name and perms.can_reorder_children():
            buttons.append(
                Button(
                    label=_("Reorder children"),
                    url=reverse(
                        self.reorder_children_url_name, args=[quote(instance.pk)]
                    ),
                    icon_name="list-ul",
                    priority=42,
                )
            )
        return buttons
