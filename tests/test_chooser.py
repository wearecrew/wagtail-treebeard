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

    def test_chooser_results_shows_root_action_for_superuser(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
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
