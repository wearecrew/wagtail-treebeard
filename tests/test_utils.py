from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from testapp.models import TreeNode
from treebeard.mp_tree import MP_Node
from wagtail_treebeard.utils import (
    apply_mp_sibling_order,
    index_url_with_parent_pk,
    insert_breadcrumbs_before_last,
    model_supports_manual_ordering,
    mp_node_breadcrumb_chain,
    mp_node_edit_breadcrumb_items,
)


class IndexUrlWithParentPkTests(SimpleTestCase):
    def test_without_parent(self) -> None:
        self.assertEqual(
            index_url_with_parent_pk("/snippets/producttype/", None),
            "/snippets/producttype/",
        )

    def test_with_parent(self) -> None:
        self.assertEqual(
            index_url_with_parent_pk("/snippets/producttype/", 42),
            "/snippets/producttype/?parent_pk=42",
        )

    def test_preserves_existing_querystring(self) -> None:
        self.assertEqual(
            index_url_with_parent_pk("/snippets/producttype/?q=hat", 42),
            "/snippets/producttype/?q=hat&parent_pk=42",
        )


class ModelSupportsManualOrderingTests(SimpleTestCase):
    def test_true_when_node_order_by_empty(self) -> None:
        class OrderedByPath(MP_Node):
            node_order_by: list[str] = []

            class Meta:
                abstract = True

        self.assertTrue(model_supports_manual_ordering(OrderedByPath))

    def test_false_when_node_order_by_set(self) -> None:
        class OrderedByName(MP_Node):
            node_order_by = ["name"]

            class Meta:
                abstract = True

        self.assertFalse(model_supports_manual_ordering(OrderedByName))


class BreadcrumbHelperTests(SimpleTestCase):
    def test_mp_node_breadcrumb_chain_includes_node(self):
        class FakeNode:
            def get_ancestors(self):
                return ["a", "b"]

        node = FakeNode()
        chain = mp_node_breadcrumb_chain(node)
        self.assertEqual(chain, ["a", "b", node])

    def test_mp_node_edit_breadcrumb_items_without_url_name(self):
        self.assertEqual(
            mp_node_edit_breadcrumb_items([object()], edit_url_name=None),
            [],
        )

    def test_insert_breadcrumbs_before_last_noop_when_short(self):
        items = [{"url": "/", "label": "Only"}]
        self.assertIs(
            insert_breadcrumbs_before_last(items, [{"url": "/x", "label": "X"}]),
            items,
        )

    def test_insert_breadcrumbs_before_last_inserts_before_final(self):
        items = [
            {"url": "/", "label": "Home"},
            {"url": "", "label": "Current"},
        ]
        extra = [{"url": "/mid", "label": "Mid"}]
        self.assertEqual(
            insert_breadcrumbs_before_last(items, extra),
            [
                {"url": "/", "label": "Home"},
                {"url": "/mid", "label": "Mid"},
                {"url": "", "label": "Current"},
            ],
        )


class ApplyMpSiblingOrderTests(TestCase):
    def test_reorders_siblings(self):
        parent = TreeNode.add_root(name="Parent")
        first = parent.add_child(name="First")
        second = parent.add_child(name="Second")
        third = parent.add_child(name="Third")

        apply_mp_sibling_order(parent, [third.pk, first.pk, second.pk])

        names = list(parent.get_children().values_list("name", flat=True))
        self.assertEqual(names, ["Third", "First", "Second"])

    def test_single_child_is_noop(self):
        parent = TreeNode.add_root(name="Solo parent")
        child = parent.add_child(name="Only")
        apply_mp_sibling_order(parent, [child.pk])
        self.assertEqual(child.get_parent(), parent)

    def test_mismatched_pks_raises_validation_error(self):
        parent = TreeNode.add_root(name="Parent")
        child = parent.add_child(name="Child")
        with self.assertRaises(ValidationError):
            apply_mp_sibling_order(parent, [child.pk, 99999])
