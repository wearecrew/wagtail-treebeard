from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


if TYPE_CHECKING:
    from treebeard.mp_tree import MP_Node

INDEX_PARENT_PK_QUERY_PARAM = "parent_pk"


def index_url_with_parent_pk(url: str, parent_pk: Any | None) -> str:
    """Append ``parent_pk`` for tree index / results URLs (explorer-style navigation)."""
    if parent_pk is None:
        return url
    query = urlencode({INDEX_PARENT_PK_QUERY_PARAM: parent_pk})
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{query}"


def model_supports_manual_ordering(model: type[MP_Node]) -> bool:
    """
    Whether drag-and-drop sibling reordering is meaningful for ``model``.

    When treebeard's :attr:`~treebeard.mp_tree.MP_Node.node_order_by` is set (e.g. ``["name"]``),
    sibling order follows those fields on insert/move; manual path reordering would fight that.
    """
    return not getattr(model, "node_order_by", None)


def mp_node_breadcrumb_chain(node: models.Model) -> list[models.Model]:
    """Ancestors root-to-parent, then ``node`` (for tree admin breadcrumbs)."""
    return list(node.get_ancestors()) + [node]


def mp_node_edit_breadcrumb_items(
    chain: list[models.Model],
    *,
    edit_url_name: str | None,
) -> list[dict[str, Any]]:
    if not edit_url_name:
        return []
    return [
        {"url": reverse(edit_url_name, args=(quote(node.pk),)), "label": str(node)}
        for node in chain
    ]


def insert_breadcrumbs_before_last(
    items: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not extra or len(items) < 2:
        return items
    return [*items[:-1], *extra, items[-1]]


def apply_mp_sibling_order(parent: MP_Node, ordered_pks: list[Any]) -> None:
    """
    Reorder direct children of ``parent`` to match ``ordered_pks`` (a permutation of child PKs)
    using treebeard ``move``, compatible with :class:`~core.models.trees.TreeModel` overrides.
    """
    model = type(parent)
    existing = set(parent.get_children().values_list("pk", flat=True))
    if set(ordered_pks) != existing or len(ordered_pks) != len(existing):
        raise ValidationError(
            _(
                "Child list does not match the current tree state; refresh and try again."
            )
        )
    if len(ordered_pks) <= 1:
        return

    with transaction.atomic():
        first = model.objects.get(pk=ordered_pks[0])
        first.move(parent, pos="first-child")
        prev_pk = ordered_pks[0]
        for pk in ordered_pks[1:]:
            prev = model.objects.get(pk=prev_pk)
            node = model.objects.get(pk=pk)
            node.move(prev, pos="right")
            prev_pk = pk
