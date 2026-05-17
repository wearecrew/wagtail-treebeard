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

    def instances_user_can_add_children_to(
        self, user: AbstractBaseUser
    ) -> models.QuerySet:
        """
        Nodes that may be chosen as the parent when creating a child.

        Subclass to apply domain filters (select-parent form, choosers, per-node checks). Default is all
        nodes, ordered by ``path``.
        """
        return self.model._default_manager.all().order_by("path")

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
        qs = self.instances_user_can_add_children_to(user)
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
            if instance.depth > 1:
                qs = qs.exclude(path=instance.path[: -self.model.steplen])
        return qs

    # --- Request-scoped helpers (admin views) ---

    def user_can_add_root(self, user: AbstractBaseUser) -> bool:
        """Whether the select-parent step may offer creating a new root node."""
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

    def instances_user_can_add_children_to(
        self, user: AbstractBaseUser
    ) -> models.QuerySet:
        if not self.user_has_permission(user, "add"):
            return self.model._default_manager.none()
        return super().instances_user_can_add_children_to(user)

    def instances_user_can_move_to(
        self,
        user: AbstractBaseUser,
        instance: models.Model | None = None,
    ) -> models.QuerySet:
        if not self.user_has_permission(user, "change"):
            return self.model._default_manager.none()
        return super().instances_user_can_move_to(user, instance)

    def user_can_add_root(self, user: AbstractBaseUser) -> bool:
        """Whether the select-parent step may offer creating a new root node."""
        if not self.user_has_permission(user, "add"):
            return False
        if self._model_has_add_root_permission:
            # Custom Meta permission uses codename ``add_root``, not ``add_root_<model>``.
            return self.user_has_permission(user, ADD_ROOT_PERMISSION_CODENAME)
        return True
