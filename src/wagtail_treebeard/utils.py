from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Case, F, Value, When
from django.db.models.functions import Concat, Substr
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from treebeard.exceptions import PathOverflow
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


def admin_display_title(instance: models.Model) -> str:
    """Resolve the admin tree label for ``instance`` (see :meth:`~wagtail_treebeard.models.TreebeardMixin.get_admin_display_title`)."""
    get_title = getattr(instance, "get_admin_display_title", None)
    if get_title is not None:
        return get_title()
    return str(instance)


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
        {
            "url": reverse(edit_url_name, args=(quote(node.pk),)),
            "label": admin_display_title(node),
        }
        for node in chain
    ]


def insert_breadcrumbs_before_last(
    items: list[dict[str, Any]],
    extra: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not extra or len(items) < 2:
        return items
    return [*items[:-1], *extra, items[-1]]


def _bulk_rewrite_subtree_paths(
    model: type[MP_Node],
    parent: MP_Node,
    mappings: list[tuple[str, str]],
) -> None:
    """
    One ``UPDATE`` applying disjoint subtree path rewrites (``Case`` / ``When``).

    Safe when each ``old_path`` is a distinct sibling root prefix under ``parent``.
    """
    mappings = [(old, new) for old, new in mappings if old != new]
    if not mappings:
        return
    # Longest/old-path-first so ``When`` branches are unambiguous; for same-depth siblings,
    # descending path order matches rolling from the highest sibling slot first.
    mappings.sort(key=lambda pair: (len(pair[0]), pair[0]), reverse=True)
    whens = [
        When(
            path__startswith=old_path,
            then=Concat(Value(new_path), Substr("path", len(old_path) + 1)),
        )
        for old_path, new_path in mappings
    ]
    for old_path, new_path in mappings:
        if len(new_path) > len(old_path):
            raise PathOverflow(f"Path Overflow from: '{old_path}'")
    model.objects.filter(
        path__startswith=parent.path,
        depth__gt=parent.depth,
    ).update(path=Case(*whens, default=F("path")))


def _sibling_roll_path_mappings(
    model: type[MP_Node],
    parent: MP_Node,
    siblings: list[MP_Node],
    old_index: int,
    new_index: int,
) -> list[tuple[str, str]]:
    """``(old_path, new_path)`` for one batched roll step opening the target gap."""
    depth = parent.depth + 1
    steplen = model.steplen
    mappings: list[tuple[str, str]] = []
    if new_index > old_index:
        indices = range(old_index + 1, new_index + 1)
        delta = -1
    else:
        indices = range(old_index - 1, new_index - 1, -1)
        delta = 1
    for index in indices:
        sibling = siblings[index]
        position = model._str2int(sibling.path[-steplen:])
        new_position = position + delta
        if new_position < 1:
            raise PathOverflow(f"Path Overflow from: '{sibling.path}'")
        new_path = model._get_path(parent.path, depth, new_position)
        mappings.append((sibling.path, new_path))
    return mappings


def _apply_roll_mappings_via_scratch(
    model: type[MP_Node],
    parent: MP_Node,
    roll_mappings: list[tuple[str, str]],
    *,
    scratch_base_position: int,
) -> None:
    """
    Apply sibling rolls in two batched ``UPDATE``s via scratch paths.

    Avoids ``path`` uniqueness clashes on SQLite when many siblings shift in one statement.
    ``scratch_base_position`` is the treebeard position already used to park the moved node.
    """
    if not roll_mappings:
        return

    depth = parent.depth + 1
    via_temp: list[tuple[str, str]] = []
    temp_to_final: list[tuple[str, str]] = []
    for index, (old_path, new_path) in enumerate(roll_mappings):
        temp_position = scratch_base_position + index + 1
        temp_path = model._get_path(parent.path, depth, temp_position)
        if len(temp_path) > len(old_path):
            previous = model._get_path(parent.path, depth, temp_position - 1)
            raise PathOverflow(f"Path Overflow from: '{previous}'")
        via_temp.append((old_path, temp_path))
        temp_to_final.append((temp_path, new_path))

    _bulk_rewrite_subtree_paths(model, parent, via_temp)
    _bulk_rewrite_subtree_paths(model, parent, temp_to_final)


def _reorder_child_by_index(
    parent: MP_Node,
    item: MP_Node,
    old_index: int,
    new_index: int,
    siblings: list[MP_Node],
) -> None:
    """
    Move ``item`` from ``old_index`` to ``new_index`` among ``siblings`` (path order, 0-based).

    1. Park ``item`` on a scratch path (vacates its old slot).
    2. Roll intervening siblings via scratch paths (two batched ``UPDATE``s).
    3. Move ``item`` from scratch into the target position.
    """
    if old_index == new_index:
        return

    model = type(parent)
    depth = parent.depth + 1
    steplen = model.steplen
    max_position = max(model._str2int(sibling.path[-steplen:]) for sibling in siblings)
    scratch_position = max_position + 1
    scratch_path = model._get_path(parent.path, depth, scratch_position)
    if len(scratch_path) > len(item.path):
        raise PathOverflow(f"Path Overflow from: '{item.path}'")

    _bulk_rewrite_subtree_paths(model, parent, [(item.path, scratch_path)])

    roll_mappings = _sibling_roll_path_mappings(
        model, parent, siblings, old_index, new_index
    )
    _apply_roll_mappings_via_scratch(
        model,
        parent,
        roll_mappings,
        scratch_base_position=scratch_position,
    )

    target_path = model._get_path(parent.path, depth, new_index + 1)
    _bulk_rewrite_subtree_paths(model, parent, [(scratch_path, target_path)])


def _reorder_mp_children_locked(
    parent: MP_Node,
    ordered_pks: list[Any],
) -> None:
    """Apply ``ordered_pks`` by repeated single-index moves (parent row already locked)."""
    model = type(parent)
    child_depth = parent.depth + 1

    while True:
        siblings = list(
            model.objects.filter(
                path__startswith=parent.path,
                depth=child_depth,
            )
            .only("pk", "path", "depth", "numchild")
            .order_by("path")
        )
        current_pks = [sibling.pk for sibling in siblings]
        if current_pks == ordered_pks:
            return
        for target_index, pk in enumerate(ordered_pks):
            if current_pks[target_index] == pk:
                continue
            item = next(sibling for sibling in siblings if sibling.pk == pk)
            old_index = current_pks.index(pk)
            _reorder_child_by_index(parent, item, old_index, target_index, siblings)
            break


def move_mp_child_to_position(
    parent: MP_Node,
    item: MP_Node,
    new_position: int,
    *,
    siblings: list[MP_Node] | None = None,
) -> None:
    """
    Move one direct child of ``parent`` to ``new_position`` (0-based, path order among siblings).

    Pass ``siblings`` when the caller already loaded them (path order).
    """
    model = type(parent)

    if siblings is None:
        siblings = list(parent.get_children().order_by("path"))
    try:
        old_position = next(
            index for index, sibling in enumerate(siblings) if sibling.pk == item.pk
        )
    except StopIteration:
        raise ValidationError(
            _(
                "Child list does not match the current tree state; refresh and try again."
            )
        )
    if new_position == old_position:
        return

    with transaction.atomic():
        locked_parent = model.objects.select_for_update().get(pk=parent.pk)
        siblings = list(locked_parent.get_children().order_by("path"))
        item = next(sibling for sibling in siblings if sibling.pk == item.pk)
        try:
            _reorder_child_by_index(
                locked_parent, item, old_position, new_position, siblings
            )
        except PathOverflow as exc:
            raise ValidationError(str(exc)) from exc


def apply_mp_sibling_order(parent: MP_Node, ordered_pks: list[Any]) -> None:
    """
    Reorder direct children of ``parent`` to match ``ordered_pks`` (a permutation of child PKs).

    Sibling-only reorder under a fixed parent: only sibling ``path`` values (and descendant
    prefixes) change. Does not use :meth:`~treebeard.mp_tree.MP_Node.move` — that API also
    adjusts old/new parents' ``numchild`` and unrelated branches; use ``move()`` for reparenting.
    """
    model = type(parent)

    with transaction.atomic():
        locked_parent = model.objects.select_for_update().get(pk=parent.pk)
        children_by_pk = {
            child.pk: child
            for child in model.objects.filter(
                path__startswith=locked_parent.path,
                depth=locked_parent.depth + 1,
            ).only("pk", "path", "depth", "numchild")
        }
        existing = set(children_by_pk)
        if set(ordered_pks) != existing or len(ordered_pks) != len(existing):
            raise ValidationError(
                _(
                    "Child list does not match the current tree state; refresh and try again."
                )
            )
        if len(ordered_pks) <= 1:
            return

        try:
            _reorder_mp_children_locked(locked_parent, ordered_pks)
        except PathOverflow as exc:
            raise ValidationError(str(exc)) from exc
