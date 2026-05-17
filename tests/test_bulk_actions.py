from django.test import TestCase
from django.urls import reverse
from django.utils.http import urlencode

from wagtail.snippets.bulk_actions.delete import DeleteBulkAction
from wagtail.test.utils import WagtailTestUtils

from testapp.models import TreeNode
from wagtail_treebeard.bulk_actions import TreebeardDeleteBulkAction


def bulk_delete_url(model, *items, next_url: str | None = None):
    query = [("id", str(item.pk)) for item in items]
    if next_url is not None:
        query.append(("next", next_url))
    return (
        reverse(
            "wagtail_bulk_action",
            args=(model._meta.app_label, model._meta.model_name, "delete"),
        )
        + "?"
        + urlencode(query)
    )


class TreebeardBulkDeleteTests(WagtailTestUtils, TestCase):
    def setUp(self):
        self.login()
        self.root = TreeNode.add_root(name="Bulk root")
        self.child = self.root.add_child(name="Bulk child")
        self.leaf = TreeNode.add_root(name="Bulk leaf")

    def test_tree_node_uses_treebeard_bulk_delete_action(self):
        from wagtail.admin.views.bulk_action.registry import bulk_action_registry

        action_class = bulk_action_registry.get_bulk_action_class(
            TreeNode._meta.app_label,
            TreeNode._meta.model_name,
            "delete",
        )
        self.assertIs(action_class, TreebeardDeleteBulkAction)
        self.assertNotEqual(action_class, DeleteBulkAction)

    def test_bulk_delete_confirmation_lists_nodes_with_children(self):
        response = self.client.get(bulk_delete_url(TreeNode, self.root, self.leaf))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "wagtail_treebeard/bulk_actions/confirm_bulk_delete.html"
        )
        self.assertContains(response, "child nodes and will not be deleted")
        self.assertContains(response, "Bulk root")
        self.assertContains(response, "Bulk leaf")

    def test_bulk_delete_skips_parents_and_deletes_leaves(self):
        next_url = reverse(TreeNode.snippet_viewset.get_url_name("list"))
        response = self.client.post(
            bulk_delete_url(TreeNode, self.root, self.leaf, next_url=next_url),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(TreeNode.objects.filter(pk=self.root.pk).exists())
        self.assertTrue(TreeNode.objects.filter(pk=self.child.pk).exists())
        self.assertFalse(TreeNode.objects.filter(pk=self.leaf.pk).exists())
        self.assertContains(
            response, "Skipped deleting 1 item because it has child nodes"
        )
        self.assertContains(response, "deleted.")

    def test_bulk_delete_only_children_selected_shows_go_back(self):
        response = self.client.get(bulk_delete_url(TreeNode, self.root))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "child nodes and will not be deleted")
        self.assertNotContains(response, "Yes, delete")

    def test_search_index_includes_bulk_actions(self):
        TreeNode.add_root(name="Findable bulk")
        response = self.client.get(
            reverse(TreeNode.snippet_viewset.get_url_name("list")),
            {"q": "Findable"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "bulk-actions.js")

    def test_explore_index_omits_bulk_actions_footer(self):
        response = self.client.get(
            reverse(
                TreeNode.snippet_viewset.get_url_name("explore"),
                args=[self.root.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Select all snippets in listing")
        self.assertNotContains(response, 'type="checkbox"')
