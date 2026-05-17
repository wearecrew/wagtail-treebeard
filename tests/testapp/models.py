from django.db import models
from treebeard.mp_tree import MP_Node

from wagtail_treebeard.models import TreebeardMixin

from .permissions import LockedNodePermissionTester, RestrictivePlacementPolicy


class TreeNode(TreebeardMixin, MP_Node):
    """Default policy and tester."""

    breadcrumb_title_fields = ("name",)
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "tree node"
        verbose_name_plural = "tree nodes"

    def __str__(self) -> str:
        return self.name


class PolicyRestrictedNode(TreebeardMixin, MP_Node):
    """Uses :class:`~testapp.permissions.RestrictivePlacementPolicy`."""

    permission_policy_class = RestrictivePlacementPolicy
    breadcrumb_title_fields = ("name",)

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


class BreadcrumbGroup(models.Model):
    name = models.CharField(max_length=255)
    internal_code = models.CharField(max_length=50, default="")


class BreadcrumbRelatedTreeNode(TreebeardMixin, MP_Node):
    """For tests of ``breadcrumb_title_fields`` relation lookups."""

    breadcrumb_title_fields = ("group__name",)
    name = models.CharField(max_length=255)
    group = models.ForeignKey(
        BreadcrumbGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tree_nodes",
    )

    class Meta:
        verbose_name = "breadcrumb related tree node"
        verbose_name_plural = "breadcrumb related tree nodes"

    def get_admin_display_title(self) -> str:
        if self.group_id:
            return self.group.name
        return self.name


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
