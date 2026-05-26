from django.contrib.admin.utils import quote
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from wagtail.test.utils import WagtailTestUtils

from testapp.models import TreeNode
from wagtail_treebeard.constants import ADD_ROOT_PERMISSION_LABEL
from testapp.wagtail_hooks import TreeNodeChooserCreationForm, TreeNodeViewSet
from test_views import assert_admin_permission_denied
from wagtail_treebeard.choosers import ChooserMode
from wagtail_treebeard.choosers.viewsets import ChooserViewSet
from wagtail_treebeard.choosers.widgets import (
    TreebeardModelChooser,
    TreebeardMoveParentChooser,
    TreebeardParentChooser,
)


def chooser_viewset(model: type[TreeNode] = TreeNode):
    return model.snippet_viewset.chooser_viewset


def chooser_results_url(model: type[TreeNode] = TreeNode) -> str:
    return reverse(chooser_viewset(model).get_url_name("choose_results"))


def chooser_explore_results_url(model: type[TreeNode], parent_pk: object) -> str:
    return reverse(
        chooser_viewset(model).get_url_name("choose_explore_results"),
        args=[parent_pk],
    )


def chooser_choose_url(model: type[TreeNode] = TreeNode) -> str:
    return reverse(chooser_viewset(model).get_url_name("choose"))


def chooser_chosen_url(model: type[TreeNode], pk: object) -> str:
    return reverse(chooser_viewset(model).get_url_name("chosen"), args=[quote(pk)])


def chooser_create_root_url(model: type[TreeNode] = TreeNode) -> str:
    return reverse(chooser_viewset(model).get_url_name("create"))


def chooser_create_child_url(model: type[TreeNode], parent_pk: object) -> str:
    return reverse(
        chooser_viewset(model).get_url_name("create_child"),
        args=[parent_pk],
    )


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
        response = self.client.get(chooser_explore_results_url(TreeNode, self.root.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse child")

    def test_invalid_chooser_mode_defaults_to_choose(self):
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": "not-a-mode"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["chooser_mode"].value, ChooserMode.CHOOSE.value
        )

    def test_parent_for_move_browse_excludes_moved_node(self):
        response = self.client.get(
            chooser_explore_results_url(TreeNode, self.child.pk),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "move_instance_pk": self.grandchild.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Browse grandchild")

    def test_parent_for_move_search_lists_valid_targets(self):
        TreeNode.add_root(name="Other root")
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
            {"chooser_mode": ChooserMode.CHOOSE, "q": "Browse root"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Browse root")


class ChooserCreationTests(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "create_admin", "create_admin@example.com", "password"
        )
        cls.root = TreeNode.add_root(name="Create root")

    def setUp(self):
        self.client.force_login(self.superuser)
        self._previous = TreeNodeViewSet.chooser_creation_form_class
        TreeNodeViewSet.chooser_creation_form_class = TreeNodeChooserCreationForm

    def tearDown(self):
        TreeNodeViewSet.chooser_creation_form_class = self._previous

    def test_browse_shows_add_root_when_enabled(self):
        response = self.client.get(chooser_results_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add root level item")
        self.assertContains(response, "treebeard-snippet-chooser-create-link")
        self.assertContains(response, chooser_create_root_url())

    def test_browse_shows_add_child_when_browsing_parent(self):
        response = self.client.get(chooser_explore_results_url(TreeNode, self.root.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add child")
        self.assertContains(response, chooser_create_child_url(TreeNode, self.root.pk))

    def test_create_root_get_renders_form(self):
        response = self.client.get(chooser_create_root_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add root level item")
        self.assertContains(response, "data-chooser-modal-creation-form")
        self.assertContains(response, "treebeard-snippet-chooser-browse-link")
        self.assertContains(response, "Cancel")
        self.assertNotContains(response, "Back to browsing")

    def test_create_child_get_shows_parent_breadcrumb_and_cancel(self):
        self.root.add_child(name="Existing child")
        response = self.client.get(chooser_create_child_url(TreeNode, self.root.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add child")
        self.assertContains(response, "Create root")
        self.assertContains(response, f"parent_pk={self.root.pk}")
        self.assertNotContains(response, "Back to browsing")

    def test_choose_with_parent_pk_opens_browse_at_level(self):
        self.root.add_child(name="Child for browse restore")
        response = self.client.get(
            chooser_choose_url(),
            {"parent_pk": self.root.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Child for browse restore")

    def test_create_root_post_creates_node_and_returns_chosen(self):
        response = self.client.post(
            chooser_create_root_url(),
            {"name": "New chooser root"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            TreeNode.objects.filter(name="New chooser root", depth=1).exists()
        )
        self.assertContains(response, '"step": "chosen"')
        self.assertContains(response, "New chooser root")

    def test_create_child_post_creates_under_parent(self):
        response = self.client.post(
            chooser_create_child_url(TreeNode, self.root.pk),
            {"name": "New chooser child"},
        )
        self.assertEqual(response.status_code, 200)
        child = TreeNode.objects.get(name="New chooser child")
        self.assertEqual(child.get_parent(), self.root)
        self.assertContains(response, '"step": "chosen"')

    def test_create_hidden_when_disabled(self):
        TreeNodeViewSet.chooser_creation_form_class = None
        response = self.client.get(chooser_results_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")

    def test_create_hidden_in_parent_for_create_mode(self):
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")
        self.assertNotContains(response, "Add child")

    def test_create_hidden_in_parent_for_move_mode(self):
        child = self.root.add_child(name="Move target child")
        response = self.client.get(
            chooser_results_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "move_instance_pk": child.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")
        self.assertNotContains(response, "Add child")

    def test_choose_modal_inline_creation_only_in_choose_mode(self):
        response = self.client.get(chooser_choose_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add root level item")
        self.assertContains(response, "treebeard-snippet-chooser-create-link")

        response = self.client.get(
            chooser_choose_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")
        self.assertNotContains(response, "treebeard-snippet-chooser-create-link")
        self.assertNotContains(response, 'id="tab-label-create"')

        child = self.root.add_child(name="Move tab child")
        response = self.client.get(
            chooser_choose_url(),
            {
                "chooser_mode": ChooserMode.PARENT_FOR_MOVE,
                "move_instance_pk": child.pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")
        self.assertNotContains(response, "treebeard-snippet-chooser-create-link")
        self.assertNotContains(response, 'id="tab-label-create"')

    def test_parent_and_move_widgets_set_non_choose_mode(self):
        self.assertNotIn(
            "chooser_mode",
            TreebeardModelChooser(TreeNode).get_chooser_modal_url(),
        )
        self.assertIn(
            ChooserMode.PARENT_FOR_CREATE,
            TreebeardParentChooser(TreeNode).get_chooser_modal_url(),
        )
        self.assertIn(
            ChooserMode.PARENT_FOR_MOVE,
            TreebeardMoveParentChooser(TreeNode, move_instance_pk=1).get_chooser_modal_url(),
        )

    def test_create_get_denied_in_parent_for_create_mode(self):
        response = self.client.get(
            chooser_create_root_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        assert_admin_permission_denied(self, response)

    def test_create_post_denied_in_parent_for_create_mode(self):
        response = self.client.post(
            f"{chooser_create_root_url()}?chooser_mode={ChooserMode.PARENT_FOR_CREATE}",
            {"name": "Should not create"},
        )
        assert_admin_permission_denied(self, response)
        self.assertFalse(TreeNode.objects.filter(name="Should not create").exists())


class ChooserCreationPermissionTests(WagtailTestUtils, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = TreeNode.add_root(name="Perm root")
        cls.add_only = User.objects.create_user("chooser_add", "chooser_add@example.com", "p")
        cls.add_root_user = User.objects.create_user(
            "chooser_add_root", "chooser_add_root@example.com", "p"
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
        add_root_perm, _ = Permission.objects.get_or_create(
            codename="add_root",
            content_type=ContentType.objects.get_for_model(TreeNode),
            defaults={"name": str(ADD_ROOT_PERMISSION_LABEL)},
        )
        cls.add_only.user_permissions.add(add_perm, access_admin)
        cls.add_root_user.user_permissions.add(add_perm, add_root_perm, access_admin)

    def setUp(self):
        self._previous = TreeNodeViewSet.chooser_creation_form_class
        TreeNodeViewSet.chooser_creation_form_class = TreeNodeChooserCreationForm

    def tearDown(self):
        TreeNodeViewSet.chooser_creation_form_class = self._previous

    def test_add_without_add_root_omits_root_create_actions(self):
        self.client.force_login(self.add_only)
        response = self.client.get(chooser_results_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Add root level item")

    def test_add_root_user_sees_root_create_actions(self):
        self.client.force_login(self.add_root_user)
        response = self.client.get(chooser_results_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add root level item")

    def test_create_root_denied_without_add_root_permission(self):
        self.client.force_login(self.add_only)
        response = self.client.get(chooser_create_root_url())
        assert_admin_permission_denied(self, response)


class ChooserViewIntegrationTests(WagtailTestUtils, TestCase):
    """Smoke tests for treebeard chooser modal and chosen endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "chooser_admin", "chooser_admin@example.com", "password"
        )
        cls.root = TreeNode.add_root(name="Chooser root")
        cls.child = cls.root.add_child(name="Chooser child")

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_choose_modal_view_loads(self):
        response = self.client.get(chooser_choose_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "wagtail_treebeard/chooser/chooser.html")

    def test_browse_navigate_link_for_node_with_children(self):
        response = self.client.get(chooser_results_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, chooser_explore_results_url(TreeNode, self.root.pk)
        )
        self.assertContains(response, f'data-parent-pk="{self.root.pk}"')

    def test_parent_for_create_lists_choose_action_for_valid_parent(self):
        response = self.client.get(
            chooser_results_url(),
            {"chooser_mode": ChooserMode.PARENT_FOR_CREATE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chooser root")
        self.assertContains(response, "data-chooser-modal-choice")

    def test_chosen_view_returns_modal_response(self):
        response = self.client.get(
            chooser_chosen_url(TreeNode, self.root.pk),
            {"chooser_mode": ChooserMode.CHOOSE},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Chooser root")
