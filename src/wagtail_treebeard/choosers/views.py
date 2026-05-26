"""Tree-aware snippet chooser (hierarchical browse + optional search)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from django.contrib.admin.utils import quote, unquote
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views import View
from wagtail.admin.modal_workflow import render_modal_workflow
from wagtail.admin.ui.tables import Column, Table
from wagtail.admin.views.generic.chooser import (
    ChooseResultsViewMixin,
    ChooseViewMixin,
    ChosenResponseMixin,
    CreateViewMixin,
    CreationFormMixin,
    PreserveURLParametersMixin,
)
from wagtail.snippets.views.chooser import BaseSnippetChooseView

from wagtail_treebeard.views import TreebeardCreateMixin

from wagtail_treebeard.utils import (
    admin_display_title,
    mp_node_breadcrumb_ancestor_list,
)

from .constants import PRESERVED_CHOOSER_PARAMS, ChooserMode


if TYPE_CHECKING:
    from django.db import models


class TreebeardChooserParamsMixin:
    """Shared chooser query parameters (mode, preserved GET params)."""

    def get_chooser_mode(self) -> ChooserMode:
        raw = self.request.GET.get("chooser_mode")
        if not raw:
            return ChooserMode.CHOOSE
        try:
            return ChooserMode(raw)
        except ValueError:
            return ChooserMode.CHOOSE

    def get_preserved_get_params(self) -> dict[str, str]:
        return {
            param: self.request.GET[param]
            for param in PRESERVED_CHOOSER_PARAMS
            if param in self.request.GET
        }

    def chooser_creation_enabled(self) -> bool:
        """Viewset opt-in only (``chooser_creation_form_class``); not a per-user check."""
        snippet_viewset = self.require_model_class().snippet_viewset
        return getattr(snippet_viewset, "chooser_creation_form_class", None) is not None

    def user_can_create_at_parent(
        self,
        user: AbstractBaseUser,
        parent: models.Model | None,
    ) -> bool:
        """Whether ``user`` may create at this tree level (policy / per-node tester)."""
        policy = self.require_model_class().permission_policy
        if parent is None:
            return policy.user_can_add_root(user)
        return parent.permissions_for_user(user).can_add_child()

    def require_model_class(self) -> type[models.Model]:
        if self.model_class is None:
            raise ImproperlyConfigured(f"{self.__class__.__name__} requires a model.")
        return self.model_class

    def chooser_inline_creation_allowed(self) -> bool:
        """
        Whether inline creation is allowed for this chooser session.

        Only :class:`~wagtail_treebeard.choosers.widgets.TreebeardModelChooser`
        uses ``ChooserMode.CHOOSE``; parent and move pickers use other modes and never
        allow the create tab or browse "Add …" actions.
        """
        if not self.chooser_creation_enabled():
            return False
        return self.get_chooser_mode() is ChooserMode.CHOOSE

    def chooser_user_can_inline_create(
        self, *, parent: models.Model | None = None
    ) -> bool:
        if not self.chooser_inline_creation_allowed():
            return False
        if parent is None:
            parent = getattr(self, "browse_parent", None)
        return self.user_can_create_at_parent(self.request.user, parent)

    def reverse_chooser_create_url(
        self, *, parent: models.Model | None = None
    ) -> str:
        if parent is None:
            url_name = self.create_url_name
            args: tuple[int | str, ...] = ()
        else:
            url_name = self.create_child_url_name
            args = (quote(parent.pk),)
        if not url_name:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing a create URL name."
            )
        return self.append_preserved_url_parameters(reverse(url_name, args=args))

    def get_choose_browse_url(self, *, parent_pk: int | str | None = None) -> str:
        """Full chooser modal URL restoring browse at ``parent_pk`` (root when omitted)."""
        if not self.choose_url_name:
            raise ImproperlyConfigured(
                f"{self.__class__.__name__} is missing choose_url_name."
            )
        params = dict(self.get_preserved_get_params())
        if parent_pk is not None:
            params["parent_pk"] = str(parent_pk)
        base = reverse(self.choose_url_name)
        if params:
            return f"{base}?{urlencode(params)}"
        return base


class ChooseResultsMixin(TreebeardChooserParamsMixin):
    """Browse MP_Node children by default; flat search when the filter form is searching."""

    results_template_name = "wagtail_treebeard/chooser/results.html"
    preserve_url_parameters = list(PRESERVED_CHOOSER_PARAMS)
    browse_parent: models.Model | None = None
    choose_explore_results_url_name: str | None = None
    choose_url_name: str | None = None
    create_url_name: str | None = None
    create_child_url_name: str | None = None

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.browse_parent = None
        parent_pk = kwargs.get("parent_pk")
        if parent_pk is None:
            parent_pk = self.request.GET.get("parent_pk")
        if parent_pk:
            self.browse_parent = get_object_or_404(
                self.require_model_class(), pk=unquote(str(parent_pk))
            )

    def get(self, request, *args: Any, **kwargs: Any):
        # ``explore/<parent_pk>/results/`` passes parent_pk; stock chooser ``get()`` does not.
        return super().get(request)

    def can_create(self) -> bool:
        return self.chooser_user_can_inline_create()

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

    def _create_actions_allowed_in_browse(self) -> bool:
        return self.chooser_inline_creation_allowed() and self.is_browse_mode

    def can_show_create_root_action(self) -> bool:
        if not self._create_actions_allowed_in_browse() or self.browse_parent is not None:
            return False
        return self.can_choose_root_for_user(self.request.user)

    def can_show_create_child_action(self) -> bool:
        if not self._create_actions_allowed_in_browse() or self.browse_parent is None:
            return False
        return self.browse_parent.permissions_for_user(
            self.request.user
        ).can_add_child()

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

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["preserved_get_params"] = self.get_preserved_get_params()
        browse_ancestors = (
            mp_node_breadcrumb_ancestor_list(self.browse_parent)
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
        show_create_root = self.can_show_create_root_action()
        show_create_child = self.can_show_create_child_action()
        context.update(
            {
                "can_show_create_root_action": show_create_root,
                "can_show_create_child_action": show_create_child,
            }
        )
        if show_create_root:
            context["create_root_url"] = self.reverse_chooser_create_url()
        if show_create_child and self.browse_parent is not None:
            context["create_child_url"] = self.reverse_chooser_create_url(
                parent=self.browse_parent
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

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["preserved_get_params"] = self.get_preserved_get_params()
        return context


class ChooseResultsView(
    ChooseResultsMixin, ChooseResultsViewMixin, BaseSnippetChooseView
):
    pass


class ChooserCreateView(
    TreebeardCreateMixin,
    TreebeardChooserParamsMixin,
    CreateViewMixin,
    CreationFormMixin,
    ChosenResponseMixin,
    PreserveURLParametersMixin,
    View,
):
    """Create a tree node inside the snippet chooser modal (opt-in via viewset)."""

    response_data_title_key = "string"
    preserve_url_parameters = list(PRESERVED_CHOOSER_PARAMS)
    template_name = "wagtail_treebeard/chooser/create_step.html"
    creation_form_template_name = "wagtail_treebeard/chooser/creation_form.html"
    create_url_name: str | None = None
    create_child_url_name: str | None = None
    choose_url_name: str | None = None
    header_icon = "folder"
    sort_order_field = None

    def get_treebeard_model(self) -> type[models.Model]:
        return self.require_model_class()

    def dispatch(self, request, *args: Any, **kwargs: Any):
        if not self.chooser_inline_creation_allowed():
            raise PermissionDenied
        parent = self.resolve_create_parent(**kwargs)
        if not self.user_can_create_at_parent(request.user, parent):
            raise PermissionDenied
        return super(CreateViewMixin, self).dispatch(request, *args, **kwargs)

    def setup(self, request, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        self.setup_create_parent(request, *args, **kwargs)

    def post(self, request, *args: Any, **kwargs: Any):
        return super().post(request)

    def get_form_class(self):
        return self.get_treebeard_form_class()

    def get_creation_form_class(self):
        return self.get_form_class()

    def get_form_kwargs(self) -> dict[str, Any]:
        return self.get_treebeard_form_kwargs()

    def get_creation_form_kwargs(self) -> dict[str, Any]:
        kwargs = super().get_creation_form_kwargs()
        kwargs.update(self.get_treebeard_form_kwargs())
        return kwargs

    def save_instance(self) -> models.Model:
        return self.save_treebeard_instance()

    def save_form(self, form):
        self.form = form
        return self.save_instance()

    def get_create_url(self) -> str:
        return self.reverse_chooser_create_url(parent=self.parent)

    def get_create_page_title(self) -> str:
        if self.parent is None:
            return str(_("Add root level item"))
        return str(_("Add child"))

    def get_create_step_breadcrumb_context(self) -> dict[str, Any]:
        browse_parent = self.parent
        ancestors = (
            mp_node_breadcrumb_ancestor_list(browse_parent)
            if browse_parent is not None
            else []
        )
        cancel_parent_pk = browse_parent.pk if browse_parent is not None else None
        return {
            "browse_parent": browse_parent,
            "browse_parent_title": (
                admin_display_title(browse_parent)
                if browse_parent is not None
                else ""
            ),
            "browse_ancestor_links": [
                {
                    "label": admin_display_title(node),
                    "url": self.get_choose_browse_url(parent_pk=node.pk),
                    "pk": node.pk,
                }
                for node in ancestors
            ],
            "browse_results_url": self.get_choose_browse_url(),
            "cancel_url": self.get_choose_browse_url(parent_pk=cancel_parent_pk),
        }

    def get(self, request, *args: Any, **kwargs: Any):
        self.form = self.get_creation_form()
        return self.render_create_step()

    def get_reshow_creation_form_response(self):
        return self.render_create_step()

    def render_create_step(self):
        context = {
            "view": self,
            "page_title": self.get_create_page_title(),
            "header_icon": self.header_icon,
        }
        context.update(self.get_create_step_breadcrumb_context())
        context.update(self.get_creation_form_context_data(self.form))
        return render_modal_workflow(
            self.request,
            self.template_name,
            None,
            context,
            json_data={"step": "choose"},
        )
