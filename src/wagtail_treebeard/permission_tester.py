"""
Per-node permission checks for tree-shaped snippets (analogous to ``PagePermissionTester``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from django.db import models

    from wagtail_treebeard.permission_policy import TreebeardPermissionPolicyMixin

from wagtail_treebeard.utils import model_supports_manual_ordering


class TreebeardPermissionTester:
    """
    Per-node permission checks for a user (mirrors :class:`wagtail.models.PagePermissionTester`).

    Subclass and set :attr:`~wagtail_treebeard.models.TreebeardMixin.permission_tester_class`
    to customise auth or workflow; override :meth:`can_move` on the model when a node must not move.
    """

    def __init__(
        self,
        user: AbstractBaseUser,
        node: models.Model,
        policy: TreebeardPermissionPolicyMixin,
    ) -> None:
        self.user = user
        self.node = node
        self.permission_policy = policy

    def can_add_child(self) -> bool:
        """Whether a new child may be created under ``self.node`` (via the permission policy)."""
        if not self.permission_policy.user_has_permission(self.user, "add"):
            return False
        return (
            self.permission_policy.instances_user_can_add_children_to(self.user)
            .filter(pk=self.node.pk)
            .exists()
        )

    def _move_target_parent_pks(self) -> set[int | str]:
        if not hasattr(self, "_move_target_parent_pks_cache"):
            self._move_target_parent_pks_cache = set(
                self.permission_policy.instances_user_can_move_to(
                    self.user, self.node
                ).values_list("pk", flat=True)
            )
        return self._move_target_parent_pks_cache

    def can_move_to(self, parent: models.Model) -> bool:
        """Whether ``self.node`` may be moved to be a direct child of ``parent`` (via the permission policy)."""
        if not self.permission_policy.user_has_permission(self.user, "change"):
            return False
        return parent.pk in self._move_target_parent_pks()

    def can_move(self) -> bool:
        """
        Whether the Move admin action and move view are available for ``self.node``.

        True when the user may change the node, :meth:`~wagtail_treebeard.models.TreebeardMixin.can_move`
        allows it, and there is at least one valid target — another parent from
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.instances_user_can_move_to`,
        or (for non-root nodes) promoting to root via
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.user_can_add_root`.
        """
        if not self.permission_policy.user_has_permission(self.user, "change"):
            return False
        if not self.node.can_move():
            return False
        if self._move_target_parent_pks():
            return True
        return self.node.depth > 1 and self.permission_policy.user_can_add_root(
            self.user
        )

    def can_reorder_children(self) -> bool:
        """Whether direct children of ``self.node`` may be drag-reordered (not used when ``node_order_by`` is set)."""
        if not model_supports_manual_ordering(type(self.node)):
            return False
        if not self.permission_policy.user_has_permission(self.user, "change"):
            return False
        return self.node.numchild > 0
