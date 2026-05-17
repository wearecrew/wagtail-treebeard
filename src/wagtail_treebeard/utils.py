from __future__ import annotations

from typing import Any

from django.contrib.admin.utils import quote
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import Case, F, Value, When
from django.db.models.functions import Concat, Substr
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from treebeard.exceptions import PathOverflow
from treebeard.mp_tree import MP_Node


# Legacy query param; index views redirect to :func:`reverse_index_explore_url`.
INDEX_PARENT_PK_QUERY_PARAM = "parent_pk"


def reverse_index_explore_url(explore_url_name: str, parent_pk: Any) -> str:
    """URL for browsing a node's children in the snippet index (path-based explorer)."""
    return reverse(explore_url_name, args=[quote(parent_pk)])


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


_MP_BREADCRUMB_METADATA_FIELD_NAMES = ("path", "depth", "numchild")


def breadcrumb_title_lookup_error_message(
    model: type[models.Model], lookup: str
) -> str | None:
    """Return an error message when ``lookup`` is invalid for ``breadcrumb_title_fields``."""
    label = model._meta.label
    current_model: type[models.Model] = model
    parts = lookup.split("__")
    for index, part in enumerate(parts):
        try:
            field = current_model._meta.get_field(part)
        except FieldDoesNotExist:
            return (
                f"{label}: breadcrumb_title_fields contains unknown lookup "
                f"{lookup!r} (failed on {part!r})."
            )
        if index == len(parts) - 1:
            return None
        if not field.is_relation or field.many_to_many:
            return (
                f"{label}: breadcrumb_title_fields lookup {lookup!r} cannot "
                f"traverse {part!r} with select_related (use forward ForeignKey "
                f"or OneToOne paths only)."
            )
        related_model = field.remote_field.model
        if related_model is None:
            return (
                f"{label}: breadcrumb_title_fields lookup {lookup!r} has "
                f"non-relational segment {part!r}."
            )
        current_model = related_model
    return None


def _breadcrumb_title_select_related_path(lookup: str) -> str | None:
    if "__" not in lookup:
        return None
    parts = lookup.split("__")
    if len(parts) < 2:
        return None
    return "__".join(parts[:-1])


def breadcrumb_title_select_related_paths(
    model: type[models.Model],
) -> tuple[str, ...]:
    """``select_related`` paths implied by :attr:`~wagtail_treebeard.models.TreebeardMixin.breadcrumb_title_fields`."""
    title_fields = getattr(model, "breadcrumb_title_fields", None)
    if not title_fields:
        return ()
    paths: list[str] = []
    seen: set[str] = set()
    for lookup in title_fields:
        path = _breadcrumb_title_select_related_path(lookup)
        if path is None or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return tuple(paths)


def breadcrumb_title_only_field_names(
    model: type[models.Model],
) -> tuple[str, ...] | None:
    """
    Column names for ``QuerySet.only()`` when loading breadcrumb ancestors.

    Returns ``None`` when :attr:`~wagtail_treebeard.models.TreebeardMixin.breadcrumb_title_fields`
    is unset (load full rows). Otherwise the primary key, MP metadata, and configured fields.
    """
    title_fields = getattr(model, "breadcrumb_title_fields", None)
    if title_fields is None:
        return None
    names: list[str] = [
        model._meta.pk.name,
        *_MP_BREADCRUMB_METADATA_FIELD_NAMES,
        *title_fields,
    ]
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name in seen:
            continue
        if name in _MP_BREADCRUMB_METADATA_FIELD_NAMES or name == model._meta.pk.name:
            model._meta.get_field(name)
        seen.add(name)
        result.append(name)
    return tuple(result)


def get_breadcrumb_ancestor_queryset(node: models.Model):
    """
    Ancestors for breadcrumb UI, optionally narrowed via ``breadcrumb_title_fields``.

    Same ordering as :meth:`~treebeard.mp_tree.MP_Node.get_ancestors`.
    """
    model = node.__class__
    queryset = node.get_ancestors()
    only_fields = breadcrumb_title_only_field_names(model)
    if only_fields is not None:
        select_related = breadcrumb_title_select_related_paths(model)
        if select_related:
            queryset = queryset.select_related(*select_related)
        queryset = queryset.only(*only_fields)
    return queryset


def mp_node_breadcrumb_ancestor_list(node: models.Model) -> list[models.Model]:
    """Ancestors root-to-parent for breadcrumb UI (via the registered snippet viewset when present)."""
    viewset = getattr(node.__class__, "snippet_viewset", None)
    if viewset is not None:
        return list(viewset.get_breadcrumb_ancestors(node))
    return list(node.get_ancestors())


def mp_node_breadcrumb_chain(node: models.Model) -> list[models.Model]:
    """Ancestors root-to-parent, then ``node`` (for tree admin breadcrumbs)."""
    return [*mp_node_breadcrumb_ancestor_list(node), node]


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


def mp_node_explore_breadcrumb_items(
    chain: list[models.Model],
    *,
    explore_url_name: str | None,
) -> list[dict[str, Any]]:
    if not explore_url_name:
        return []
    return [
        {
            "url": reverse_index_explore_url(explore_url_name, node.pk),
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
    *,
    anchor_path: str,
    anchor_depth: int,
    mappings: list[tuple[str, str]],
) -> None:
    """
    One ``UPDATE`` applying disjoint subtree path rewrites (``Case`` / ``When``).

    Safe when each ``old_path`` is a distinct sibling root prefix under the anchor.
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
        path__startswith=anchor_path,
        depth__gt=anchor_depth,
    ).update(path=Case(*whens, default=F("path")))


def _sibling_roll_path_mappings(
    model: type[MP_Node],
    *,
    anchor_path: str,
    anchor_depth: int,
    siblings: list[MP_Node],
    old_index: int,
    new_index: int,
) -> list[tuple[str, str]]:
    """``(old_path, new_path)`` for one batched roll step opening the target gap."""
    depth = anchor_depth + 1
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
        new_path = model._get_path(anchor_path, depth, new_position)
        mappings.append((sibling.path, new_path))
    return mappings


def _apply_roll_mappings_via_scratch(
    model: type[MP_Node],
    *,
    anchor_path: str,
    anchor_depth: int,
    roll_mappings: list[tuple[str, str]],
    scratch_base_position: int,
) -> None:
    """
    Apply sibling rolls in two batched ``UPDATE``s via scratch paths.

    Avoids ``path`` uniqueness clashes on SQLite when many siblings shift in one statement.
    ``scratch_base_position`` is the treebeard position already used to park the moved node.
    """
    if not roll_mappings:
        return

    depth = anchor_depth + 1
    via_temp: list[tuple[str, str]] = []
    temp_to_final: list[tuple[str, str]] = []
    for index, (old_path, new_path) in enumerate(roll_mappings):
        temp_position = scratch_base_position + index + 1
        temp_path = model._get_path(anchor_path, depth, temp_position)
        if len(temp_path) > len(old_path):
            previous = model._get_path(anchor_path, depth, temp_position - 1)
            raise PathOverflow(f"Path Overflow from: '{previous}'")
        via_temp.append((old_path, temp_path))
        temp_to_final.append((temp_path, new_path))

    _bulk_rewrite_subtree_paths(
        model, anchor_path=anchor_path, anchor_depth=anchor_depth, mappings=via_temp
    )
    _bulk_rewrite_subtree_paths(
        model,
        anchor_path=anchor_path,
        anchor_depth=anchor_depth,
        mappings=temp_to_final,
    )


def _reorder_sibling_by_index(
    model: type[MP_Node],
    *,
    anchor_path: str,
    anchor_depth: int,
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

    depth = anchor_depth + 1
    steplen = model.steplen
    max_position = max(model._str2int(sibling.path[-steplen:]) for sibling in siblings)
    scratch_position = max_position + 1
    scratch_path = model._get_path(anchor_path, depth, scratch_position)
    if len(scratch_path) > len(item.path):
        raise PathOverflow(f"Path Overflow from: '{item.path}'")

    _bulk_rewrite_subtree_paths(
        model,
        anchor_path=anchor_path,
        anchor_depth=anchor_depth,
        mappings=[(item.path, scratch_path)],
    )

    roll_mappings = _sibling_roll_path_mappings(
        model,
        anchor_path=anchor_path,
        anchor_depth=anchor_depth,
        siblings=siblings,
        old_index=old_index,
        new_index=new_index,
    )
    _apply_roll_mappings_via_scratch(
        model,
        anchor_path=anchor_path,
        anchor_depth=anchor_depth,
        roll_mappings=roll_mappings,
        scratch_base_position=scratch_position,
    )

    target_path = model._get_path(anchor_path, depth, new_index + 1)
    _bulk_rewrite_subtree_paths(
        model,
        anchor_path=anchor_path,
        anchor_depth=anchor_depth,
        mappings=[(scratch_path, target_path)],
    )


def _reorder_mp_siblings_locked(
    model: type[MP_Node],
    *,
    anchor_path: str,
    anchor_depth: int,
    sibling_depth: int,
    ordered_pks: list[Any],
) -> None:
    """Apply ``ordered_pks`` by repeated single-index moves (siblings already locked)."""
    while True:
        siblings = list(
            model.objects.filter(
                path__startswith=anchor_path,
                depth=sibling_depth,
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
            _reorder_sibling_by_index(
                model,
                anchor_path=anchor_path,
                anchor_depth=anchor_depth,
                item=item,
                old_index=old_index,
                new_index=target_index,
                siblings=siblings,
            )
            break


def _lock_root_siblings(model: type[MP_Node]) -> list[MP_Node]:
    return list(model.get_root_nodes().select_for_update().order_by("path"))


def move_mp_child_to_position(
    parent: MP_Node,
    item: MP_Node,
    new_position: int,
    *,
    siblings: list[MP_Node] | None = None,
) -> None:
    """
    Reorder one direct child of ``parent`` to ``new_position`` (0-based, path order among siblings).

    Pass ``siblings`` when the caller already loaded them (path order). Path-order update only,
    not a reparenting :meth:`~treebeard.mp_tree.MP_Node.move`.
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
        ) from None
    if new_position == old_position:
        return

    with transaction.atomic():
        locked_parent = model.objects.select_for_update().get(pk=parent.pk)
        siblings = list(locked_parent.get_children().order_by("path"))
        locked_item = next(sibling for sibling in siblings if sibling.pk == item.pk)
        try:
            _reorder_sibling_by_index(
                model,
                anchor_path=locked_parent.path,
                anchor_depth=locked_parent.depth,
                item=locked_item,
                old_index=old_position,
                new_index=new_position,
                siblings=siblings,
            )
        except PathOverflow as exc:
            raise ValidationError(str(exc)) from exc


def move_mp_root_to_position(
    item: MP_Node,
    new_position: int,
    *,
    siblings: list[MP_Node] | None = None,
) -> None:
    """
    Reorder one root node to ``new_position`` (0-based, path order among roots).

    Pass ``siblings`` when the caller already loaded them (path order).
    """
    model = type(item)

    if siblings is None:
        siblings = list(model.get_root_nodes().order_by("path"))
    try:
        old_position = next(
            index for index, sibling in enumerate(siblings) if sibling.pk == item.pk
        )
    except StopIteration:
        raise ValidationError(
            _("Root list does not match the current tree state; refresh and try again.")
        ) from None
    if new_position == old_position:
        return

    with transaction.atomic():
        siblings = _lock_root_siblings(model)
        locked_item = next(sibling for sibling in siblings if sibling.pk == item.pk)
        try:
            _reorder_sibling_by_index(
                model,
                anchor_path="",
                anchor_depth=0,
                item=locked_item,
                old_index=old_position,
                new_index=new_position,
                siblings=siblings,
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
            _reorder_mp_siblings_locked(
                model,
                anchor_path=locked_parent.path,
                anchor_depth=locked_parent.depth,
                sibling_depth=locked_parent.depth + 1,
                ordered_pks=ordered_pks,
            )
        except PathOverflow as exc:
            raise ValidationError(str(exc)) from exc


def apply_mp_root_sibling_order(model: type[MP_Node], ordered_pks: list[Any]) -> None:
    """
    Reorder root nodes to match ``ordered_pks`` (a permutation of root PKs).

    Same path-rewrite strategy as :func:`apply_mp_sibling_order`, using the virtual tree anchor
    at depth 0.
    """
    with transaction.atomic():
        _lock_root_siblings(model)
        roots_by_pk = {
            root.pk: root
            for root in model.objects.filter(depth=1).only(
                "pk", "path", "depth", "numchild"
            )
        }
        existing = set(roots_by_pk)
        if set(ordered_pks) != existing or len(ordered_pks) != len(existing):
            raise ValidationError(
                _(
                    "Root list does not match the current tree state; refresh and try again."
                )
            )
        if len(ordered_pks) <= 1:
            return

        try:
            _reorder_mp_siblings_locked(
                model,
                anchor_path="",
                anchor_depth=0,
                sibling_depth=1,
                ordered_pks=ordered_pks,
            )
        except PathOverflow as exc:
            raise ValidationError(str(exc)) from exc
