"""
Tree-shaped snippet permissions: model-level Django auth plus MP_Node placement rules.

:class:`TreebeardModelPermissionPolicy` handles auth and bulk querysets for choosers/forms.
Per-node checks go through :class:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester`
via :meth:`~wagtail_treebeard.models.TreebeardMixin.permissions_for_user`,
mirroring :class:`wagtail.permission_policies.pages.PagePermissionPolicy` and
:class:`wagtail.models.PagePermissionTester`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.permission_policies.base import ModelPermissionPolicy

from wagtail_treebeard.constants import ADD_ROOT_PERMISSION_CODENAME
from wagtail_treebeard.utils import model_supports_manual_ordering


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.db import models

    from wagtail_treebeard.permission_tester import TreebeardPermissionTester


class TreebeardPermissionPolicyMixin:
    def permissions_for_user(
        self,
        user: AbstractBaseUser,
        node: models.Model,
    ) -> TreebeardPermissionTester:
        """Build a per-node tester using ``node``'s :attr:`~wagtail_treebeard.models.TreebeardMixin.permission_tester_class`."""
        return node.permissions_for_user(user, policy=self)

    def instances_user_can_change(self, user: AbstractBaseUser) -> models.QuerySet:
        """Instances the user may change (subclasses should override via ``instances_user_has_permission_for``)."""
        return self.model._default_manager.none()

    def instances_user_can_add_children_to(
        self, user: AbstractBaseUser
    ) -> models.QuerySet:
        """
        Nodes that may be chosen as the parent when creating a child.

        Subclass to apply domain filters (select-parent form, choosers, per-node checks). Default is all
        nodes the user may change, ordered by ``path``.
        """
        return self.instances_user_can_change(user).order_by("path")

    def instances_user_can_move_to(
        self,
        user: AbstractBaseUser,
        instance: models.Model | None = None,
    ) -> models.QuerySet:
        """
        Nodes that may be chosen as the new parent when moving ``instance``.

        When ``instance`` is given, ``instance`` and its current parent are excluded. Subclass for
        further domain filters (node type, gender, etc.); call ``super()`` first when ``instance`` is
        set so those exclusions still apply.
        """
        qs = self.instances_user_can_change(user).order_by("path")
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
            if instance.depth > 1:
                qs = qs.exclude(path=instance.path[: -self.model.steplen])
        return qs

    def changeable_siblings_queryset(
        self,
        user: AbstractBaseUser,
        *,
        parent: models.Model | None = None,
    ) -> models.QuerySet:
        """Changeable nodes among siblings at this level (roots when ``parent`` is omitted)."""
        return self.model._default_manager.none()

    def user_can_add_root(self, user: AbstractBaseUser) -> bool:
        """Whether the select-parent step may offer creating a new root node."""
        return False

    def user_can_reorder_siblings_at_level(
        self,
        user: AbstractBaseUser,
        *,
        parent: models.Model | None = None,
    ) -> bool:
        """Whether drag-reordering is allowed among siblings at this level (``parent``'s children, or roots)."""
        return False

    def user_can_reorder_roots(self, user: AbstractBaseUser) -> bool:
        """Whether root items may be drag-reordered in the admin."""
        return False


class TreebeardModelPermissionPolicy(
    TreebeardPermissionPolicyMixin, ModelPermissionPolicy
):
    """
    Extends :class:`~wagtail.permission_policies.base.ModelPermissionPolicy` with tree placement
    helpers. :class:`~wagtail_treebeard.models.TreebeardMixin` uses this policy by default.
    """

    @property
    def _model_has_add_root_permission(self) -> bool:
        """Whether this model opts in to the optional ``add_root`` custom permission."""
        return any(
            codename == ADD_ROOT_PERMISSION_CODENAME
            for codename, _ in self.model._meta.permissions
        )

    def instances_user_can_change(self, user: AbstractBaseUser) -> models.QuerySet:
        return self.instances_user_has_permission_for(user, "change")

    def instances_user_can_add_children_to(
        self, user: AbstractBaseUser
    ) -> models.QuerySet:
        if not self.user_has_permission(user, "add"):
            return self.model._default_manager.none()
        return super().instances_user_can_add_children_to(user)

    def changeable_siblings_queryset(
        self,
        user: AbstractBaseUser,
        *,
        parent: models.Model | None = None,
    ) -> models.QuerySet:
        """
        Siblings listed on the reorder screen at this level (roots when ``parent`` is omitted).

        Gated by ``change`` on ``parent`` for child reorder, or model-level ``change`` for roots —
        not by per-child ``change``. Reordering only updates path order under a fixed parent.
        """
        if parent is not None:
            if not self.user_has_permission_for_instance(user, "change", parent):
                return self.model._default_manager.none()
            return self.model.objects.filter(
                path__startswith=parent.path,
                depth=parent.depth + 1,
            ).order_by("path")
        if not self.user_has_permission(user, "change"):
            return self.model._default_manager.none()
        return self.model.objects.filter(depth=1).order_by("path")

    def user_can_add_root(self, user: AbstractBaseUser) -> bool:
        """Whether the select-parent step may offer creating a new root node."""
        if not self.user_has_permission(user, "add"):
            return False
        if self._model_has_add_root_permission:
            # Custom Meta permission uses codename ``add_root``, not ``add_root_<model>``.
            opts = self.model._meta
            return user.has_perm(f"{opts.app_label}.{ADD_ROOT_PERMISSION_CODENAME}")
        return True

    def user_can_reorder_siblings_at_level(
        self,
        user: AbstractBaseUser,
        *,
        parent: models.Model | None = None,
    ) -> bool:
        """
        Whether drag-reordering is allowed among siblings at this level.

        Child reorder: manual ordering, ``change`` on the parent, and ``parent.numchild >= 2``.
        Root reorder: manual ordering, model-level ``change``, and at least two root nodes.
        Sibling path order is updated under a fixed parent; this is not per-child ``change``.
        """
        if not model_supports_manual_ordering(self.model):
            return False
        if parent is not None:
            if parent.numchild < 2:
                return False
            return self.user_has_permission_for_instance(user, "change", parent)
        if not self.user_has_permission(user, "change"):
            return False
        return self.model.get_root_nodes().count() >= 2

    def user_can_reorder_roots(self, user: AbstractBaseUser) -> bool:
        return self.user_can_reorder_siblings_at_level(user, parent=None)
