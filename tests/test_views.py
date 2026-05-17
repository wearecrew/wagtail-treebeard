"""Integration tests for treebeard snippet admin views."""

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from wagtail.test.utils import WagtailTestUtils

from testapp.models import TesterLockedNode, TreeNode
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy


def snippet_url(model: type, view_name: str, *args: object) -> str:
    return reverse(model.snippet_viewset.get_url_name(view_name), args=args)


def assert_admin_permission_denied(test_case: TestCase, response) -> None:
    """Wagtail admin turns PermissionDenied into a redirect to the dashboard."""
    test_case.assertEqual(response.status_code, 302)
    test_case.assertEqual(response["Location"], reverse("wagtailadmin_home"))


class TreebeardAdminViewTests(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.editor = User.objects.create_user(
            "editor", "editor@example.com", "password"
        )
        access_admin = Permission.objects.get(
            codename="access_admin",
            content_type__app_label="wagtailadmin",
            content_type__model="admin",
        )
        cls.editor.user_permissions.add(access_admin)
        for model_name in ("treenode", "testerlockednode"):
            for action in ("add", "change", "delete"):
                perm = Permission.objects.get(
                    codename=f"{action}_{model_name}",
                    content_type__app_label="testapp",
                    content_type__model=model_name,
                )
                cls.editor.user_permissions.add(perm)

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_viewset_uses_treebeard_permission_policy(self):
        policy = TreeNode.snippet_viewset.permission_policy
        self.assertIsInstance(policy, TreebeardModelPermissionPolicy)

    def test_create_child_under_parent(self):
        parent = TreeNode.add_root(name="Parent")
        url = snippet_url(TreeNode, "add_child", parent.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, {"name": "Child"})
        self.assertEqual(response.status_code, 302)
        child = TreeNode.objects.get(name="Child")
        self.assertEqual(child.get_parent(), parent)

    def test_create_root_via_add_root_url(self):
        url = snippet_url(TreeNode, "add_root")
        response = self.client.post(url, {"name": "Root"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(TreeNode.objects.filter(name="Root", depth=1).exists())

    def test_move_denied_for_locked_node(self):
        locked = TesterLockedNode.add_root(name="Locked", is_locked=True)
        url = snippet_url(TesterLockedNode, "move", locked.pk)
        response = self.client.get(url)
        assert_admin_permission_denied(self, response)

    def test_delete_denied_when_node_has_children(self):
        parent = TreeNode.add_root(name="Parent")
        parent.add_child(name="Child")
        url = snippet_url(TreeNode, "delete", parent.pk)
        response = self.client.get(url)
        assert_admin_permission_denied(self, response)

    def test_delete_allowed_for_leaf_node(self):
        parent = TreeNode.add_root(name="Leaf")
        url = snippet_url(TreeNode, "delete", parent.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_reorder_children_denied_for_locked_parent(self):
        locked = TesterLockedNode.add_root(name="Locked parent", is_locked=True)
        locked.add_child(name="Child")
        url = snippet_url(TesterLockedNode, "reorder_children", locked.pk)
        response = self.client.get(url)
        assert_admin_permission_denied(self, response)

    def test_reorder_children_allowed_for_unlocked_parent(self):
        parent = TesterLockedNode.add_root(name="Unlocked parent", is_locked=False)
        parent.add_child(name="Child one")
        parent.add_child(name="Child two")
        url = snippet_url(TesterLockedNode, "reorder_children", parent.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Child one")

    def test_confirm_add_position_lists_parent_step(self):
        TreeNode.add_root(name="Existing root")
        url = snippet_url(TreeNode, "add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a parent")
