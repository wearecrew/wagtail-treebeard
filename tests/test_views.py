"""Integration tests for treebeard snippet admin views."""

import json

from django.contrib.admin.utils import quote
from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from wagtail.test.utils import WagtailTestUtils

from testapp.models import PolicyRestrictedNode, TesterLockedNode, TreeNode
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy
from wagtail_treebeard.utils import INDEX_PARENT_PK_QUERY_PARAM


POLICY = TreebeardModelPermissionPolicy


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
        locked.add_child(name="Child one")
        locked.add_child(name="Child two")
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

    def test_confirm_add_position_post_redirects_to_add_child(self):
        parent = TreeNode.add_root(name="Pick me")
        url = snippet_url(TreeNode, "add")
        response = self.client.post(url, {"parent": parent.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            snippet_url(TreeNode, "add_child", parent.pk),
        )

    def test_index_browse_children_with_parent_pk(self):
        parent = TreeNode.add_root(name="Index parent")
        parent.add_child(name="Index child")
        url = (
            f"{snippet_url(TreeNode, 'list')}?{INDEX_PARENT_PK_QUERY_PARAM}={parent.pk}"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Index child")
        self.assertContains(response, "Index parent")
        self.assertNotContains(response, 'aria-label="Tree location"')

    def test_index_browse_explore_link_uses_table_base_url(self):
        root = TreeNode.add_root(name="Browse root")
        root.add_child(name="Browse child")
        response = self.client.get(snippet_url(TreeNode, "list"))
        self.assertEqual(response.status_code, 200)
        explore_url = (
            f"{snippet_url(TreeNode, 'list')}?{INDEX_PARENT_PK_QUERY_PARAM}={root.pk}"
        )
        self.assertContains(response, explore_url)
        self.assertContains(response, "Explore children of")
        self.assertContains(response, "Title")
        self.assertNotContains(response, "Get admin display title")

    def test_index_search_lists_matching_nodes(self):
        TreeNode.add_root(name="Findable")
        url = snippet_url(TreeNode, "list")
        response = self.client.get(url, {"q": "Find"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Findable")

    def test_index_shows_move_action_for_movable_child(self):
        root = TreeNode.add_root(name="Move root")
        child = root.add_child(name="Movable")
        url = f"{snippet_url(TreeNode, 'list')}?{INDEX_PARENT_PK_QUERY_PARAM}={root.pk}"
        response = self.client.get(url)
        self.assertContains(response, snippet_url(TreeNode, "move", child.pk))

    def test_move_get_shows_form(self):
        root = TreeNode.add_root(name="Root")
        child = root.add_child(name="To move")
        TreeNode.add_root(name="Target root")
        response = self.client.get(snippet_url(TreeNode, "move", child.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose a new parent")

    def test_move_under_new_parent(self):
        root = TreeNode.add_root(name="From root")
        child = root.add_child(name="Moving")
        target = TreeNode.add_root(name="Target")
        url = snippet_url(TreeNode, "move", child.pk)
        response = self.client.post(url, {"new_parent": str(target.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            snippet_url(TreeNode, "list"),
        )
        child.refresh_from_db()
        self.assertEqual(child.get_parent(), target)

    def test_move_to_root(self):
        root = TreeNode.add_root(name="Only root")
        child = root.add_child(name="Promote me")
        url = snippet_url(TreeNode, "move", child.pk)
        response = self.client.post(url, {"move_to_root": "1"})
        self.assertEqual(response.status_code, 302)
        child.refresh_from_db()
        self.assertEqual(child.depth, 1)

    def test_reorder_child_row_invalid_child(self):
        parent = TesterLockedNode.add_root(name="Reorder parent", is_locked=False)
        parent.add_child(name="Own child one")
        parent.add_child(name="Own child two")
        other = TesterLockedNode.add_root(name="Other", is_locked=False)
        stray = other.add_child(name="Stray")
        url = reverse(
            TesterLockedNode.snippet_viewset.get_url_name("reorder_children_row"),
            args=[quote(parent.pk), quote(stray.pk)],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(json.loads(response.content)["success"])

    def test_reorder_children_redirects_when_no_children(self):
        parent = TesterLockedNode.add_root(name="Empty", is_locked=False)
        url = snippet_url(TesterLockedNode, "reorder_children", parent.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            f"{snippet_url(TesterLockedNode, 'list')}?{INDEX_PARENT_PK_QUERY_PARAM}={parent.pk}",
        )

    def test_reorder_children_lists_all_children(self):
        parent = TreeNode.add_root(name="Parent")
        parent.add_child(name="Child A")
        parent.add_child(name="Child B")
        parent.add_child(name="Child C")
        url = snippet_url(TreeNode, "reorder_children", parent.pk)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Child A")
        self.assertContains(response, "Child B")
        self.assertContains(response, "Child C")

    def test_reorder_root_entries_allowed_with_multiple_roots(self):
        TreeNode.add_root(name="Root one")
        TreeNode.add_root(name="Root two")
        url = snippet_url(TreeNode, "reorder_root_entries")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Root one")

    def test_reorder_root_entries_redirects_when_single_root(self):
        TreeNode.add_root(name="Lonely")
        url = snippet_url(TreeNode, "reorder_root_entries")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], snippet_url(TreeNode, "list"))

    def test_index_shows_reorder_roots_header_at_root_level(self):
        TreeNode.add_root(name="Root A")
        TreeNode.add_root(name="Root B")
        response = self.client.get(snippet_url(TreeNode, "list"))
        self.assertContains(response, snippet_url(TreeNode, "reorder_root_entries"))
        self.assertContains(response, "Reorder root entries")

    def test_index_shows_reorder_header_when_browsing_parent(self):
        parent = TreeNode.add_root(name="Reorder header parent")
        parent.add_child(name="Child one")
        parent.add_child(name="Child two")
        url = (
            f"{snippet_url(TreeNode, 'list')}?{INDEX_PARENT_PK_QUERY_PARAM}={parent.pk}"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, snippet_url(TreeNode, "reorder_children", parent.pk)
        )
        self.assertContains(response, "Reorder")

    def test_reorder_root_entry_row_invalid_non_root(self):
        parent = TreeNode.add_root(name="Parent")
        child = parent.add_child(name="Child")
        url = reverse(
            TreeNode.snippet_viewset.get_url_name("reorder_root_entry_row"),
            args=[quote(child.pk)],
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(json.loads(response.content)["success"])

    def test_edit_view_includes_ancestor_breadcrumbs(self):
        root = TreeNode.add_root(name="Crumb root")
        child = root.add_child(name="Crumb child")
        response = self.client.get(snippet_url(TreeNode, "edit", child.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crumb root")

    def test_edit_view_uses_admin_display_title_for_header(self):
        root = TreeNode.add_root(name="Public name")
        original = TreeNode.get_admin_display_title

        def editor_title(self):
            return f"Editor: {self.name}"

        TreeNode.get_admin_display_title = editor_title  # type: ignore[method-assign]
        self.addCleanup(lambda: setattr(TreeNode, "get_admin_display_title", original))
        response = self.client.get(snippet_url(TreeNode, "edit", root.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Editor: Public name")

    def test_delete_leaf_post(self):
        node = TreeNode.add_root(name="Delete me")
        url = snippet_url(TreeNode, "delete", node.pk)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TreeNode.objects.filter(pk=node.pk).exists())

    def test_create_root_denied_without_add_root_permission(self):
        self.client.force_login(self.editor)
        url = snippet_url(TreeNode, "add_root")
        response = self.client.post(url, {"name": "Nope"})
        assert_admin_permission_denied(self, response)


class ReorderChildRowIntegrationTests(TreebeardAdminViewTests):
    """POST reorder_children_row: five siblings, varied drag targets (0-based positions)."""

    SIBLING_NAMES = ("One", "Two", "Three", "Four", "Five")

    def _parent_with_five_children(self):
        parent = TesterLockedNode.add_root(name="Reorder parent", is_locked=False)
        children = {name: parent.add_child(name=name) for name in self.SIBLING_NAMES}
        return parent, children

    def _reorder_children_row_url(self, parent, child) -> str:
        return reverse(
            TesterLockedNode.snippet_viewset.get_url_name("reorder_children_row"),
            args=(quote(parent.pk), quote(child.pk)),
        )

    def _post_reorder(self, parent, child, position: int) -> None:
        url = f"{self._reorder_children_row_url(parent, child)}?position={position}"
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200, response.content)
        data = json.loads(response.content)
        self.assertTrue(data["success"], data)

    def _assert_sibling_names(self, parent, expected: tuple[str, ...]) -> None:
        names = tuple(parent.get_children().values_list("name", flat=True))
        self.assertEqual(names, expected)

    def test_reorder_first_sibling_to_last_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["One"], 4)
        self._assert_sibling_names(parent, ("Two", "Three", "Four", "Five", "One"))

    def test_reorder_first_sibling_to_third_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["One"], 2)
        self._assert_sibling_names(parent, ("Two", "Three", "One", "Four", "Five"))

    def test_reorder_last_sibling_to_first_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["Five"], 0)
        self._assert_sibling_names(parent, ("Five", "One", "Two", "Three", "Four"))

    def test_reorder_last_sibling_to_second_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["Five"], 1)
        self._assert_sibling_names(parent, ("One", "Five", "Two", "Three", "Four"))

    def test_reorder_third_sibling_to_first_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["Three"], 0)
        self._assert_sibling_names(parent, ("Three", "One", "Two", "Four", "Five"))

    def test_reorder_third_sibling_to_last_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["Three"], 4)
        self._assert_sibling_names(parent, ("One", "Two", "Four", "Five", "Three"))

    def test_reorder_third_sibling_to_second_place(self):
        parent, children = self._parent_with_five_children()
        self._post_reorder(parent, children["Three"], 1)
        self._assert_sibling_names(parent, ("One", "Three", "Two", "Four", "Five"))


class ConfirmAddRedirectTests(WagtailTestUtils, TestCase):
    """Add step redirects to add_root when the user may add roots but no nodes exist yet."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("adder", "adder@example.com", "password")
        access_admin = Permission.objects.get(
            codename="access_admin",
            content_type__app_label="wagtailadmin",
            content_type__model="admin",
        )
        add_perm = Permission.objects.get(
            codename="add_policyrestrictednode",
            content_type__app_label="testapp",
            content_type__model="policyrestrictednode",
        )
        add_root_perm = Permission.objects.get(
            codename="add_root",
            content_type__app_label="testapp",
            content_type__model="policyrestrictednode",
        )
        cls.user.user_permissions.add(access_admin, add_perm, add_root_perm)

    def setUp(self):
        self.client.force_login(self.user)

    def test_add_redirects_to_add_root_when_no_valid_parents(self):
        PolicyRestrictedNode.objects.all().delete()
        url = snippet_url(PolicyRestrictedNode, "add")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response["Location"],
            snippet_url(PolicyRestrictedNode, "add_root"),
        )
