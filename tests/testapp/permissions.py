"""Custom permission policy / tester classes for override tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy
from wagtail_treebeard.permission_tester import TreebeardPermissionTester


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.db import models


class RestrictivePlacementPolicy(TreebeardModelPermissionPolicy):
    """Only nodes flagged for placement appear as valid parents."""

    def instances_user_can_add_children_to(
        self, user: AbstractBaseUser
    ) -> models.QuerySet:
        return (
            super()
            .instances_user_can_add_children_to(user)
            .filter(accept_children=True)
        )

    def instances_user_can_move_to(
        self,
        user: AbstractBaseUser,
        instance: models.Model | None = None,
    ) -> models.QuerySet:
        if not self.user_has_permission(user, "change"):
            return self.model._default_manager.none()
        qs = self.model._default_manager.filter(accept_moves_as_target=True).order_by(
            "path"
        )
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
            if instance.depth > 1:
                qs = qs.exclude(path=instance.path[: -self.model.steplen])
        return qs


class LockedNodePermissionTester(TreebeardPermissionTester):
    """Locked nodes cannot gain children, move, or have children reordered."""

    def can_add_child(self) -> bool:
        if getattr(self.node, "is_locked", False):
            return False
        return super().can_add_child()

    def can_move(self) -> bool:
        if getattr(self.node, "is_locked", False):
            return False
        return super().can_move()

    def can_reorder_children(self) -> bool:
        if getattr(self.node, "is_locked", False):
            return False
        return super().can_reorder_children()
