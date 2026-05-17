from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from treebeard.mp_tree import MP_Node

from testapp.models import TreeNode
from wagtail_treebeard.utils import (
    admin_display_title,
    apply_mp_root_sibling_order,
    apply_mp_sibling_order,
    insert_breadcrumbs_before_last,
    model_supports_manual_ordering,
    move_mp_child_to_position,
    move_mp_root_to_position,
    mp_node_breadcrumb_chain,
    mp_node_edit_breadcrumb_items,
    mp_node_explore_breadcrumb_items,
    reverse_index_explore_url,
)


class ReverseIndexExploreUrlTests(TestCase):
    def test_reverse_explore_url(self) -> None:
        url = reverse_index_explore_url(
            TreeNode.snippet_viewset.get_url_name("explore"), 42
        )
        self.assertIn("/explore/42/", url)

    def test_mp_node_explore_breadcrumb_items(self) -> None:
        root = TreeNode.add_root(name="Crumb root")
        items = mp_node_explore_breadcrumb_items(
            [root],
            explore_url_name=TreeNode.snippet_viewset.get_url_name("explore"),
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["label"], "Crumb root")
        self.assertIn("/explore/", items[0]["url"])


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


class AdminDisplayTitleTests(TestCase):
    def test_defaults_to_str(self):
        node = TreeNode.add_root(name="Shown in admin")
        self.assertEqual(node.get_admin_display_title(), "Shown in admin")
        self.assertEqual(admin_display_title(node), "Shown in admin")

    def test_override_used_in_helper(self):
        node = TreeNode.add_root(name="Public name")
        node.get_admin_display_title = lambda: "Editor label"  # type: ignore[method-assign]
        self.assertEqual(admin_display_title(node), "Editor label")


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

    def test_mp_node_explore_breadcrumb_items_without_url_name(self) -> None:
        self.assertEqual(
            mp_node_explore_breadcrumb_items([object()], explore_url_name=None),
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

    def test_reorder_preserves_descendant_paths(self):
        parent = TreeNode.add_root(name="Parent")
        first = parent.add_child(name="First")
        grandchild = first.add_child(name="Grandchild")
        second = parent.add_child(name="Second")

        apply_mp_sibling_order(parent, [second.pk, first.pk])

        grandchild.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(grandchild.get_parent(), first)
        self.assertTrue(grandchild.path.startswith(first.path))


class MpSiblingReorderTests(TestCase):
    """
    ``apply_mp_sibling_order`` / ``move_mp_child_to_position`` only (no HTTP).

    Each drag uses four path ``UPDATE``s (park, roll-to-scratch, roll-to-final, place) plus
    locking/loading — independent of how many siblings are rolled.
    """

    SIBLING_NAMES = ("One", "Two", "Three", "Four", "Five")

    def setUp(self):
        self.parent = TreeNode.add_root(name="Parent")
        self.children = {
            name: self.parent.add_child(name=name) for name in self.SIBLING_NAMES
        }
        self._parent_numchild = self.parent.numchild
        self._child_numchildren = {
            name: self.children[name].numchild for name in self.SIBLING_NAMES
        }
        self._siblings = list(self.parent.get_children().order_by("path"))

    def _reorder_to_position(
        self, child_name: str, new_position: int, *, num_queries: int
    ):
        child = self.children[child_name]
        with self.assertNumQueries(num_queries):
            move_mp_child_to_position(
                self.parent,
                child,
                new_position,
                siblings=self._siblings,
            )

    def _assert_order(self, expected: tuple[str, ...]) -> None:
        names = tuple(self.parent.get_children().values_list("name", flat=True))
        self.assertEqual(names, expected)

    def _assert_numchild_unchanged(self) -> None:
        self.parent.refresh_from_db()
        self.assertEqual(self.parent.numchild, self._parent_numchild)
        for name in self.SIBLING_NAMES:
            self.children[name].refresh_from_db()
            self.assertEqual(
                self.children[name].numchild, self._child_numchildren[name]
            )

    def test_first_sibling_to_last_place(self):
        self._reorder_to_position("One", 4, num_queries=8)
        self._assert_order(("Two", "Three", "Four", "Five", "One"))
        self._assert_numchild_unchanged()

    def test_first_sibling_to_third_place(self):
        self._reorder_to_position("One", 2, num_queries=8)
        self._assert_order(("Two", "Three", "One", "Four", "Five"))
        self._assert_numchild_unchanged()

    def test_last_sibling_to_first_place(self):
        self._reorder_to_position("Five", 0, num_queries=8)
        self._assert_order(("Five", "One", "Two", "Three", "Four"))
        self._assert_numchild_unchanged()

    def test_last_sibling_to_second_place(self):
        self._reorder_to_position("Five", 1, num_queries=8)
        self._assert_order(("One", "Five", "Two", "Three", "Four"))
        self._assert_numchild_unchanged()

    def test_third_sibling_to_first_place(self):
        self._reorder_to_position("Three", 0, num_queries=8)
        self._assert_order(("Three", "One", "Two", "Four", "Five"))
        self._assert_numchild_unchanged()

    def test_third_sibling_to_last_place(self):
        self._reorder_to_position("Three", 4, num_queries=8)
        self._assert_order(("One", "Two", "Four", "Five", "Three"))
        self._assert_numchild_unchanged()

    def test_third_sibling_to_second_place(self):
        self._reorder_to_position("Three", 1, num_queries=8)
        self._assert_order(("One", "Three", "Two", "Four", "Five"))
        self._assert_numchild_unchanged()

    def test_same_position_is_noop_without_queries(self):
        with self.assertNumQueries(0):
            move_mp_child_to_position(
                self.parent,
                self.children["Three"],
                2,
                siblings=self._siblings,
            )
        self._assert_order(self.SIBLING_NAMES)


class ApplyMpRootSiblingOrderTests(TestCase):
    def test_reorders_roots(self):
        first = TreeNode.add_root(name="First")
        second = TreeNode.add_root(name="Second")
        third = TreeNode.add_root(name="Third")

        apply_mp_root_sibling_order(TreeNode, [third.pk, first.pk, second.pk])

        names = list(TreeNode.get_root_nodes().values_list("name", flat=True))
        self.assertEqual(names, ["Third", "First", "Second"])

    def test_single_root_is_noop(self):
        only = TreeNode.add_root(name="Only")
        apply_mp_root_sibling_order(TreeNode, [only.pk])
        self.assertEqual(only.get_root().pk, only.pk)

    def test_mismatched_pks_raises_validation_error(self):
        only = TreeNode.add_root(name="Only")
        with self.assertRaises(ValidationError):
            apply_mp_root_sibling_order(TreeNode, [only.pk, 99999])

    def test_reorder_preserves_descendant_paths(self):
        first = TreeNode.add_root(name="First")
        child = first.add_child(name="Child")
        second = TreeNode.add_root(name="Second")

        apply_mp_root_sibling_order(TreeNode, [second.pk, first.pk])

        child.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(child.get_parent(), first)
        self.assertTrue(child.path.startswith(first.path))


class MpRootReorderTests(TestCase):
    SIBLING_NAMES = ("One", "Two", "Three", "Four", "Five")

    def setUp(self):
        self.roots = {name: TreeNode.add_root(name=name) for name in self.SIBLING_NAMES}
        self._siblings = list(TreeNode.get_root_nodes().order_by("path"))

    def _reorder_to_position(
        self, root_name: str, new_position: int, *, num_queries: int
    ):
        root = self.roots[root_name]
        with self.assertNumQueries(num_queries):
            move_mp_root_to_position(root, new_position, siblings=self._siblings)

    def _assert_order(self, expected: tuple[str, ...]) -> None:
        names = tuple(TreeNode.get_root_nodes().values_list("name", flat=True))
        self.assertEqual(names, expected)

    def test_third_root_to_second_place(self):
        self._reorder_to_position("Three", 1, num_queries=7)
        self._assert_order(("One", "Three", "Two", "Four", "Five"))
