"""
Model mixin for tree-shaped Wagtail snippets (django-treebeard ``MP_Node``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.db.models.signals import class_prepared
from django.dispatch import receiver
from django.utils.functional import classproperty

from wagtail_treebeard.constants import (
    ADD_ROOT_PERMISSION,
    ADD_ROOT_PERMISSION_CODENAME,
)
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy
from wagtail_treebeard.permission_tester import TreebeardPermissionTester


if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser

    from wagtail_treebeard.permission_policy import TreebeardPermissionPolicyMixin


class TreebeardMixin(models.Model):
    """
    Primary integration point for :class:`~wagtail_treebeard.viewsets.WagtailTreebeardSnippetViewSet`.

    Inherit alongside an ``MP_Node`` base (e.g. :class:`core.models.TreeModel`). Register the model
    with a :class:`~wagtail_treebeard.viewsets.WagtailTreebeardSnippetViewSet` subclass.

    Provides :meth:`permissions_for_user` (mirrors :meth:`wagtail.models.Page.permissions_for_user`).

    Override :meth:`can_move` on the model when a specific node must not be moved at all.
    Subclass :attr:`permission_tester_class` when you need to change auth or workflow;
    subclass :attr:`permission_policy_class` to restrict valid parents for create/move (choosers, forms, POST checks).

    Each concrete subclass gets :data:`ADD_ROOT_PERMISSION` on ``Meta.permissions`` by default (via
    :func:`register_wagtail_treabeard_permissions`). Set :attr:`register_add_root_permission` to ``False`` to
    omit it (root create then requires model ``add`` only).
    """

    permission_policy_class: ClassVar[type[TreebeardPermissionPolicyMixin]] = (
        TreebeardModelPermissionPolicy
    )
    permission_tester_class: ClassVar[type[TreebeardPermissionTester]] = (
        TreebeardPermissionTester
    )
    register_add_root_permission: ClassVar[bool] = True

    class Meta:
        abstract = True

    def permissions_for_user(
        self,
        user: AbstractBaseUser,
        *,
        policy: TreebeardPermissionPolicyMixin | None = None,
    ) -> TreebeardPermissionTester:
        """
        Per-node permission checks for ``user`` on this instance.

        Returns a :class:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester`
        (mirrors :meth:`wagtail.models.Page.permissions_for_user`). The tester combines Django
        model permissions with tree placement rules from
        :attr:`permission_policy` — e.g. :meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_add_child`,
        :meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_move`, and
        :meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_reorder_children`.

        Used wherever the admin needs a decision about **this** node: snippet index row actions
        (Add child, Move, Reorder children), the explore column's add-child link, chooser rows in
        create/move parent mode (:meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_add_child`
        / :meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_move_to`), and reorder
        views. For bulk querysets (parent pickers, search) use :attr:`permission_policy` instead.

        Pass ``policy`` when the caller already has a policy instance (e.g.
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.permissions_for_user`
        on the policy) so policy and tester stay aligned.

        Subclass :attr:`permission_tester_class` to customise per-node rules; subclass
        :attr:`permission_policy_class` to change which parents are valid tree-wide.
        """
        if policy is None:
            policy = self.permission_policy
        return self.permission_tester_class(user, self, policy)

    def get_admin_display_title(self) -> str:
        """
        Label for this node in Wagtail tree admin UI (index browse, chooser, breadcrumbs).

        Defaults to :meth:`~django.db.models.Model.__str__`. Override when the public
        ``__str__`` should differ from what editors see while navigating the tree.
        """
        return str(self)

    @classproperty
    def permission_policy(cls) -> TreebeardPermissionPolicyMixin:
        """
        Model-level permission policy for this tree snippet type.

        Handles Django auth (``add``, ``change``, ``delete``, optional ``add_root``) and
        **querysets** of valid parents — not decisions on a single row. Admin views read it via
        :class:`~wagtail_treebeard.views.TreebeardViewMixin` for the select-parent step, create/move
        forms, and POST validation
        (:meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.instances_user_can_add_children_to`,
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.instances_user_can_move_to`,
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.user_can_add_root`).
        Choosers use the same querysets when searching or filtering by mode.

        A fresh instance is built on each access (``@classproperty`` is intentionally uncached).
        Subclass :attr:`permission_policy_class` to restrict valid parents for create/move across
        the admin; use :meth:`permissions_for_user` when you need per-node UI or chooser row checks.
        """
        return cls.permission_policy_class(cls)

    def can_move(self) -> bool:
        """
        Domain-only: whether this node may be moved at all (before choosing a target parent).

        Used when :meth:`~wagtail_treebeard.permission_tester.TreebeardPermissionTester.can_move`
        runs after the user has model ``change`` permission — e.g. showing the "Move" action on the
        index and opening the move view. Valid move targets come from
        :meth:`~wagtail_treebeard.permission_policy.TreebeardPermissionPolicyMixin.instances_user_can_move_to`
        on :attr:`permission_policy_class`.

        Override to forbid moving certain nodes (e.g. locked or root-only types) regardless of parent.
        """
        return True


@receiver(class_prepared)
def register_wagtail_treabeard_permissions(
    sender: type[models.Model], **kwargs: object
) -> None:
    """Add or remove ``add_root`` on ``Meta.permissions`` for concrete :class:`TreebeardMixin` subclasses."""
    if not issubclass(sender, TreebeardMixin) or sender._meta.abstract:
        return
    opts = sender._meta
    without_add_root = [
        perm for perm in opts.permissions if perm[0] != ADD_ROOT_PERMISSION_CODENAME
    ]
    if sender.register_add_root_permission is False:
        opts.permissions = without_add_root
        return
    if ADD_ROOT_PERMISSION_CODENAME in {codename for codename, _ in opts.permissions}:
        return
    opts.permissions = [*without_add_root, ADD_ROOT_PERMISSION]
