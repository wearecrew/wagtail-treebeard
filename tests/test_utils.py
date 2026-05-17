from django.test import SimpleTestCase
from treebeard.mp_tree import MP_Node

from wagtail_treebeard.utils import (
    index_url_with_parent_pk,
    model_supports_manual_ordering,
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
