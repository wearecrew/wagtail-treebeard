from django.db import models
from treebeard.mp_tree import MP_Node

from wagtail_treebeard.models import TreebeardMixin

from .permissions import LockedNodePermissionTester, RestrictivePlacementPolicy


class TreeNode(TreebeardMixin, MP_Node):
    """Default policy and tester."""

    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "tree node"
        verbose_name_plural = "tree nodes"

    def __str__(self) -> str:
        return self.name


class PolicyRestrictedNode(TreebeardMixin, MP_Node):
    """Uses :class:`~testapp.permissions.RestrictivePlacementPolicy`."""

    permission_policy_class = RestrictivePlacementPolicy

    name = models.CharField(max_length=255)
    accept_children = models.BooleanField(default=True)
    accept_moves_as_target = models.BooleanField(default=True)

    class Meta:
        verbose_name = "policy restricted node"
        verbose_name_plural = "policy restricted nodes"

    def __str__(self) -> str:
        return self.name


class TesterLockedNode(TreebeardMixin, MP_Node):
    """Uses :class:`~testapp.permissions.LockedNodePermissionTester`."""

    permission_tester_class = LockedNodePermissionTester

    name = models.CharField(max_length=255)
    is_locked = models.BooleanField(default=False)

    class Meta:
        verbose_name = "tester locked node"
        verbose_name_plural = "tester locked nodes"

    def __str__(self) -> str:
        return self.name

    def can_move(self) -> bool:
        return not self.is_locked


class CombinedCustomNode(TreebeardMixin, MP_Node):
    """Both custom policy and tester."""

    permission_policy_class = RestrictivePlacementPolicy
    permission_tester_class = LockedNodePermissionTester

    name = models.CharField(max_length=255)
    accept_children = models.BooleanField(default=True)
    accept_moves_as_target = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False)

    class Meta:
        verbose_name = "combined custom node"
        verbose_name_plural = "combined custom nodes"

    def __str__(self) -> str:
        return self.name

    def can_move(self) -> bool:
        return not self.is_locked
