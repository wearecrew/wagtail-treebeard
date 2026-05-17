from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase

from testapp.models import (
    CombinedCustomNode,
    PolicyRestrictedNode,
    TesterLockedNode,
    TreeNode,
)
from testapp.permissions import LockedNodePermissionTester, RestrictivePlacementPolicy
from wagtail_treebeard.constants import ADD_ROOT_PERMISSION_LABEL
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy
from wagtail_treebeard.permission_tester import TreebeardPermissionTester


class PermissionClassWiringTests(TestCase):
    def test_default_model_uses_stock_classes(self):
        self.assertIs(TreeNode.permission_policy_class, TreebeardModelPermissionPolicy)
        self.assertIs(TreeNode.permission_tester_class, TreebeardPermissionTester)

    def test_policy_restricted_model_uses_custom_policy(self):
        self.assertIs(
            PolicyRestrictedNode.permission_policy_class, RestrictivePlacementPolicy
        )
        self.assertIs(
            PolicyRestrictedNode.permission_tester_class, TreebeardPermissionTester
        )

    def test_tester_locked_model_uses_custom_tester(self):
        self.assertIs(
            TesterLockedNode.permission_policy_class, TreebeardModelPermissionPolicy
        )
        self.assertIs(
            TesterLockedNode.permission_tester_class, LockedNodePermissionTester
        )

    def test_combined_model_uses_both_custom_classes(self):
        self.assertIs(
            CombinedCustomNode.permission_policy_class, RestrictivePlacementPolicy
        )
        self.assertIs(
            CombinedCustomNode.permission_tester_class, LockedNodePermissionTester
        )

    def test_permissions_for_user_returns_custom_tester_instance(self):
        user = User.objects.create_user("tester", "tester@example.com", "password")
        node = TesterLockedNode.add_root(name="Root")

        perms = node.permissions_for_user(user)

        self.assertIsInstance(perms, LockedNodePermissionTester)
        self.assertIsInstance(perms.permission_policy, TreebeardModelPermissionPolicy)

    def test_policy_permissions_for_user_uses_model_tester_class(self):
        user = User.objects.create_user("policy", "policy@example.com", "password")
        node = TesterLockedNode.add_root(name="Root")
        policy = TesterLockedNode.permission_policy

        perms = policy.permissions_for_user(user, node)

        self.assertIsInstance(perms, LockedNodePermissionTester)
        self.assertIs(perms.node, node)


class RestrictivePlacementPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("editor", "editor@example.com", "password")
        change_perm = Permission.objects.get(
            codename="change_policyrestrictednode",
            content_type__app_label="testapp",
            content_type__model="policyrestrictednode",
        )
        add_perm = Permission.objects.get(
            codename="add_policyrestrictednode",
            content_type__app_label="testapp",
            content_type__model="policyrestrictednode",
        )
        cls.user.user_permissions.add(change_perm, add_perm)

        cls.open_parent = PolicyRestrictedNode.add_root(
            name="Open",
            accept_children=True,
            accept_moves_as_target=True,
        )
        cls.closed_parent = PolicyRestrictedNode.add_root(
            name="Closed",
            accept_children=False,
            accept_moves_as_target=False,
        )
        cls.move_only = PolicyRestrictedNode.add_root(
            name="Move only",
            accept_children=False,
            accept_moves_as_target=True,
        )
        cls.child = cls.open_parent.add_child(name="Child")

    def test_instances_user_can_add_children_to_respects_accept_children(self):
        policy = PolicyRestrictedNode.permission_policy
        pks = set(
            policy.instances_user_can_add_children_to(self.user).values_list(
                "pk", flat=True
            )
        )

        self.assertIn(self.open_parent.pk, pks)
        self.assertNotIn(self.closed_parent.pk, pks)
        self.assertNotIn(self.move_only.pk, pks)

    def test_instances_user_can_move_to_respects_accept_moves_as_target(self):
        policy = PolicyRestrictedNode.permission_policy
        pks = set(
            policy.instances_user_can_move_to(self.user, self.child).values_list(
                "pk", flat=True
            )
        )

        self.assertNotIn(self.open_parent.pk, pks)  # current parent
        self.assertIn(self.move_only.pk, pks)
        self.assertNotIn(self.closed_parent.pk, pks)

    def test_can_add_child_follows_policy_queryset(self):
        open_perms = self.open_parent.permissions_for_user(self.user)
        closed_perms = self.closed_parent.permissions_for_user(self.user)

        self.assertTrue(open_perms.can_add_child())
        self.assertFalse(closed_perms.can_add_child())

    def test_can_move_to_follows_policy_queryset(self):
        child_perms = self.child.permissions_for_user(self.user)

        self.assertTrue(child_perms.can_move_to(self.move_only))
        self.assertFalse(child_perms.can_move_to(self.closed_parent))

    def test_can_move_when_only_move_to_root_is_available(self):
        add_root_perm = Permission.objects.get(
            codename="add_root",
            content_type__app_label="testapp",
            content_type__model="policyrestrictednode",
        )
        self.user.user_permissions.add(add_root_perm)

        only_parent = PolicyRestrictedNode.add_root(
            name="Only parent",
            accept_children=True,
            accept_moves_as_target=True,
        )
        child = only_parent.add_child(name="Sole child")
        perms = child.permissions_for_user(self.user)

        self.assertFalse(perms.can_move_to(only_parent))
        self.assertTrue(perms.can_move())


class LockedNodePermissionTesterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("editor", "editor@example.com", "password")
        change_perm = Permission.objects.get(
            codename="change_testerlockednode",
            content_type__app_label="testapp",
            content_type__model="testerlockednode",
        )
        add_perm = Permission.objects.get(
            codename="add_testerlockednode",
            content_type__app_label="testapp",
            content_type__model="testerlockednode",
        )
        cls.user.user_permissions.add(change_perm, add_perm)

        cls.unlocked = TesterLockedNode.add_root(name="Unlocked", is_locked=False)
        cls.locked = TesterLockedNode.add_root(name="Locked", is_locked=True)
        cls.locked.add_child(name="Locked child")
        cls.unlocked.add_child(name="Unlocked child")

    def test_locked_node_can_move_domain_check(self):
        self.assertFalse(self.locked.can_move())
        self.assertTrue(self.unlocked.can_move())

    def test_locked_node_tester_denies_add_child(self):
        perms = self.locked.permissions_for_user(self.user)
        self.assertFalse(perms.can_add_child())

    def test_unlocked_node_tester_allows_add_child(self):
        perms = self.unlocked.permissions_for_user(self.user)
        self.assertTrue(perms.can_add_child())

    def test_locked_node_tester_denies_move(self):
        perms = self.locked.permissions_for_user(self.user)
        self.assertFalse(perms.can_move())

    def test_locked_parent_tester_denies_reorder_children(self):
        perms = self.locked.permissions_for_user(self.user)
        self.assertFalse(perms.can_reorder_children())

    def test_unlocked_parent_tester_allows_reorder_children(self):
        perms = self.unlocked.permissions_for_user(self.user)
        self.assertTrue(perms.can_reorder_children())


class CombinedCustomOverridesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("editor", "editor@example.com", "password")
        change_perm = Permission.objects.get(
            codename="change_combinedcustomnode",
            content_type__app_label="testapp",
            content_type__model="combinedcustomnode",
        )
        add_perm = Permission.objects.get(
            codename="add_combinedcustomnode",
            content_type__app_label="testapp",
            content_type__model="combinedcustomnode",
        )
        cls.user.user_permissions.add(change_perm, add_perm)

        cls.parent = CombinedCustomNode.add_root(
            name="Parent",
            accept_children=True,
            accept_moves_as_target=True,
            is_locked=False,
        )
        cls.no_children = CombinedCustomNode.add_root(
            name="No children",
            accept_children=False,
            accept_moves_as_target=False,
            is_locked=False,
        )
        cls.locked = CombinedCustomNode.add_root(name="Locked", is_locked=True)
        cls.move_target = CombinedCustomNode.add_root(
            name="Move target",
            accept_children=True,
            accept_moves_as_target=True,
            is_locked=False,
        )
        cls.child = cls.parent.add_child(name="Child")

    def test_policy_and_tester_both_apply(self):
        child_perms = self.child.permissions_for_user(self.user)

        self.assertFalse(
            self.no_children.permissions_for_user(self.user).can_add_child()
        )
        self.assertTrue(self.parent.permissions_for_user(self.user).can_add_child())
        self.assertTrue(child_perms.can_move_to(self.move_target))
        self.assertFalse(child_perms.can_move_to(self.parent))  # current parent
        self.assertFalse(child_perms.can_move_to(self.no_children))
        self.assertFalse(self.locked.permissions_for_user(self.user).can_move())


class TreebeardModelPermissionPolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.policy = TreeNode.permission_policy
        cls.add_only = User.objects.create_user("addonly", "addonly@example.com", "p")
        cls.change_only = User.objects.create_user(
            "changeonly", "changeonly@example.com", "p"
        )
        cls.add_root_user = User.objects.create_user(
            "rooter", "rooter@example.com", "p"
        )
        cls.add_perm = Permission.objects.get(
            codename="add_treenode",
            content_type__app_label="testapp",
            content_type__model="treenode",
        )
        cls.change_perm = Permission.objects.get(
            codename="change_treenode",
            content_type__app_label="testapp",
            content_type__model="treenode",
        )
        cls.add_root_perm, _ = Permission.objects.get_or_create(
            codename="add_root",
            content_type=ContentType.objects.get_for_model(TreeNode),
            defaults={"name": str(ADD_ROOT_PERMISSION_LABEL)},
        )
        cls.add_only.user_permissions.add(cls.add_perm)
        cls.change_only.user_permissions.add(cls.change_perm)
        cls.add_root_user.user_permissions.add(cls.add_perm, cls.add_root_perm)

        cls.root = TreeNode.add_root(name="Root")
        cls.child = cls.root.add_child(name="Child")

    def test_instances_user_can_add_children_to_empty_without_add(self):
        qs = self.policy.instances_user_can_add_children_to(self.change_only)
        self.assertEqual(qs.count(), 0)

    def test_instances_user_can_move_to_empty_without_change(self):
        qs = self.policy.instances_user_can_move_to(self.add_only, self.child)
        self.assertEqual(qs.count(), 0)

    def test_instances_user_can_move_to_excludes_self_and_parent(self):
        qs = self.policy.instances_user_can_move_to(self.change_only, self.child)
        pks = set(qs.values_list("pk", flat=True))
        self.assertNotIn(self.child.pk, pks)
        self.assertNotIn(self.root.pk, pks)

    def test_user_can_add_root_requires_add_root_permission_when_registered(self):
        self.assertFalse(self.policy.user_can_add_root(self.add_only))
        self.assertTrue(self.policy.user_can_add_root(self.add_root_user))

    def test_tester_denies_move_without_change_permission(self):
        perms = self.child.permissions_for_user(self.add_only)
        self.assertFalse(perms.can_move())
        self.assertFalse(perms.can_move_to(self.root))
        self.assertFalse(perms.can_reorder_children())

    def test_tester_denies_reorder_without_change_permission(self):
        parent = TreeNode.add_root(name="Reorder parent")
        parent.add_child(name="A")
        parent.add_child(name="B")
        perms = parent.permissions_for_user(self.add_only)
        self.assertFalse(perms.can_reorder_children())

    def test_tester_allows_reorder_with_change_permission(self):
        parent = TreeNode.add_root(name="Reorder parent 2")
        parent.add_child(name="A")
        parent.add_child(name="B")
        perms = parent.permissions_for_user(self.change_only)
        self.assertTrue(perms.can_reorder_children())
