from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from wagtail.test.utils import WagtailTestUtils

from testapp.models import TreeNode
from wagtail_treebeard.choosers import ChooserMode
from wagtail_treebeard.choosers.viewsets import ChooserViewSet


def chooser_results_url(model: type[TreeNode] = TreeNode) -> str:
    viewset = model.snippet_viewset.chooser_viewset
    return reverse(viewset.get_url_name("choose_results"))


class CanChooseRootTests(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "admin", "admin@example.com", "password"
        )
        cls.editor = User.objects.create_user(
            "editor", "editor@example.com", "password"
        )
        add_perm = Permission.objects.get(
            codename="add_treenode",
            content_type__app_label="testapp",
            content_type__model="treenode",
        )
        access_admin = Permission.objects.get(
            codename="access_admin",
            content_type__app_label="wagtailadmin",
            content_type__model="admin",
        )
        cls.editor.user_permissions.add(add_perm, access_admin)
        TreeNode.add_root(name="Existing root")

    def test_viewset_reflects_add_root_permission(self):
        viewset = ChooserViewSet("test_chooser", model=TreeNode)

        self.assertTrue(viewset.can_choose_root_for_user(self.superuser))
        self.assertFalse(viewset.can_choose_root_for_user(self.editor))

    def test_chooser_results_omits_root_action_without_add_root(self):
        self.client.login(username="editor", password="password")
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "treebeard-snippet-chooser-clear-parent")

    def test_chooser_results_hides_root_action_by_default(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "treebeard-snippet-chooser-clear-parent")

    def test_chooser_results_shows_root_action_when_enabled(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_CREATE,
                "show_choose_root_option": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "treebeard-snippet-chooser-clear-parent")

    def test_can_choose_root_not_in_preserved_url_params(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_CREATE,
                "can_choose_root": "1",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("can_choose_root", response.context["preserved_get_params"])
        self.assertNotIn(
            "can_choose_root=1",
            response.context["browse_results_url"],
        )


class ChooserBrowseAndSearchTests(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "admin2", "admin2@example.com", "password"
        )
        cls.root = TreeNode.add_root(name="Browse root")
        cls.child = cls.root.add_child(name="Browse child")
        cls.grandchild = cls.child.add_child(name="Browse grandchild")

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_browse_children_with_parent_pk(self):
        response = self.client.get(
            chooser_results_url(),
            {"parent_pk": self.root.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse child")

    def test_invalid_chooser_mode_defaults_to_choose(self):
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": "not-a-mode"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["chooser_mode"].value, ChooserMode.CHOOSE.value)

    def test_parent_for_move_browse_excludes_moved_node(self):
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "move_instance_pk": self.grandchild.pk,
                "parent_pk": self.child.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Browse grandchild")

    def test_parent_for_move_search_lists_valid_targets(self):
        other_root = TreeNode.add_root(name="Other root")
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "move_instance_pk": self.grandchild.pk,
                "q": "Other",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other root")

    def test_parent_for_move_search_without_instance_returns_404(self):
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "q": "Browse",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_choose_mode_search(self):
        response = self.client.get(
            chooser_results_url(),
            {"q": "Browse grand"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse grandchild")
