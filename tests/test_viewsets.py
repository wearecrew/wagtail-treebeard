from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from treebeard.mp_tree import MP_Node
from wagtail.test.utils import WagtailTestUtils

from testapp.models import TreeNode
from wagtail_treebeard.choosers.viewsets import ChooserViewSet
from wagtail_treebeard.viewsets import WagtailTreebeardSnippetViewSet


def snippet_url(model: type, view_name: str, *args: object) -> str:
    return reverse(model.snippet_viewset.get_url_name(view_name), args=args)


class NotTreebeard(MP_Node):
    class Meta:
        app_label = "testapp"


class WagtailTreebeardSnippetViewSetTests(SimpleTestCase):
    def test_rejects_model_without_treebeard_mixin(self):
        with self.assertRaises(ImproperlyConfigured):
            WagtailTreebeardSnippetViewSet(model=User)

    def test_rejects_mp_node_without_treebeard_mixin(self):
        with self.assertRaises(ImproperlyConfigured):
            WagtailTreebeardSnippetViewSet(model=NotTreebeard)


class TreebeardSnippetViewSetIntegrationTests(WagtailTestUtils, TestCase):
    """Smoke tests for a registered :class:`WagtailTreebeardSnippetViewSet`."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            "vs_admin", "vs_admin@example.com", "password"
        )

    def setUp(self):
        self.client.force_login(self.superuser)

    def test_registers_treebeard_chooser_viewset(self):
        chooser = TreeNode.snippet_viewset.chooser_viewset
        self.assertIsInstance(chooser, ChooserViewSet)
        self.assertIs(chooser.model, TreeNode)

    def test_form_excludes_treebeard_mp_fields(self):
        exclude = TreeNode.snippet_viewset.get_exclude_form_fields()
        for field_name in ("path", "depth", "numchild"):
            self.assertIn(field_name, exclude)

    def test_registered_admin_urls_load(self):
        parent = TreeNode.add_root(name="Viewset root")
        child = parent.add_child(name="Viewset child")
        parent.add_child(name="Viewset sibling")
        TreeNode.add_root(name="Viewset root two")
        urls = [
            snippet_url(TreeNode, "list"),
            snippet_url(TreeNode, "add"),
            snippet_url(TreeNode, "add_root"),
            snippet_url(TreeNode, "add_child", parent.pk),
            snippet_url(TreeNode, "edit", parent.pk),
            snippet_url(TreeNode, "move", child.pk),
            snippet_url(TreeNode, "reorder_children", parent.pk),
            snippet_url(TreeNode, "reorder_root_items"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_index_uses_treebeard_listing_template(self):
        response = self.client.get(snippet_url(TreeNode, "list"))
        self.assertTemplateUsed(response, "wagtail_treebeard/index.html")
