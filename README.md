# wagtail-treebeard

[![Ruff](https://github.com/torchbox/wagtail-treebeard/actions/workflows/ruff.yml/badge.svg)](https://github.com/torchbox/wagtail-treebeard/actions/workflows/ruff.yml)
[![Build status](https://github.com/torchbox/wagtail-treebeard/actions/workflows/test.yml/badge.svg)](https://github.com/torchbox/wagtail-treebeard/actions/workflows/test.yml)

An add-on for managing treebeard `MP_Node`-based snippet models in Wagtail.

Requires **Wagtail 6.0+** (child reordering relies on snippet listing reorder support added in Wagtail 6).

## Supported versions

- Python 3.11, 3.12, 3.13, 3.14
- Django 4.2, 5.0, 5.2, 6.0 (see [Wagtail’s compatibility table](https://docs.wagtail.org/en/stable/releases/upgrading.html#compatible-django-python-versions) for each Wagtail release)
- **Minimum** Wagtail 6.0 (snippet reorder); **LTS** Wagtail 7 ([7.0 LTS](https://docs.wagtail.org/en/stable/releases/7.0.html), [7.4 LTS](https://docs.wagtail.org/en/stable/releases/7.4.html) — see the [release index](https://docs.wagtail.org/en/stable/releases/index.html))
- CI also exercises Wagtail 6.3 as a representative 6.x release

## Installation

```bash
pip install wagtail-treebeard
```

Add `wagtail_treebeard` to `INSTALLED_APPS` (before `wagtail` is fine; it must be listed).

## Quick start

Define a snippet model that combines `TreebeardMixin` with django-treebeard’s `MP_Node`, then register it with `WagtailTreebeardSnippetViewSet` instead of the stock `SnippetViewSet`:

```python
from django.db import models
from treebeard.mp_tree import MP_Node
from wagtail.snippets.models import register_snippet

from wagtail_treebeard.models import TreebeardMixin
from wagtail_treebeard.viewsets import WagtailTreebeardSnippetViewSet


class Category(TreebeardMixin, MP_Node):
    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "category"
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class CategoryViewSet(WagtailTreebeardSnippetViewSet):
    model = Category
    icon = "folder"
    menu_label = "Categories"
    add_to_admin_menu = True


register_snippet(Category, viewset=CategoryViewSet)
```

The admin then provides:

- Explorer-style index (browse children level-by-level; search lists the matching subtree)
- Create via “choose parent” (or add at root)
- Per-row **Add child**, **Move**, and **Reorder children** (when manual ordering applies)
- Delete blocked while `numchild > 0`

**Bulk delete is intentionally disabled** on the snippet index (no bulk-actions column or footer). Deleting a node with children would bypass per-node rules; remove or reparent children first.

## Permissions

Tree operations use two extension points (mirroring Wagtail’s page permission policy / tester pattern):

| Layer | Class attribute | Use for |
|-------|-----------------|---------|
| Model-wide querysets | `permission_policy_class` (default `TreebeardModelPermissionPolicy`) | Which nodes may be parents for create/move; Django `add` / `change` / `delete`; optional `add_root` |
| Per-node UI / chooser rows | `permission_tester_class` (default `TreebeardPermissionTester`) | Whether this user may add a child under, move, or reorder this node |

**Domain rules on a single instance** — override `can_move()` on the model when a node must never be moved (e.g. locked rows), regardless of parent.

**Root creation** — concrete models get an `add_root` permission on `Meta.permissions` by default. Users need that permission (or only `add` if you set `register_add_root_permission = False` on the model) to create top-level nodes or use “move to root”.

Subclass examples:

```python
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy
from wagtail_treebeard.permission_tester import TreebeardPermissionTester


class CategoryPermissionPolicy(TreebeardModelPermissionPolicy):
    def instances_user_can_add_children_to(self, user):
        return super().instances_user_can_add_children_to(user).filter(is_active=True)


class CategoryPermissionTester(TreebeardPermissionTester):
    def can_add_child(self):
        if self.node.is_full:
            return False
        return super().can_add_child()


class Category(TreebeardMixin, MP_Node):
    permission_policy_class = CategoryPermissionPolicy
    permission_tester_class = CategoryPermissionTester
    # ...
```

## Chooser

Parent pickers (create, move, and `TreebeardParentChooser` / `TreebeardMoveParentChooser`) use a hierarchical chooser:

- **Browse** — one tree level per page; row actions respect per-node permissions.
- **Search** — flat list filtered by the same policy querysets as the admin forms.

Configure page size on your viewset (default **50** for treebeard snippets, vs **10** on stock `SnippetViewSet`):

```python
class CategoryViewSet(WagtailTreebeardSnippetViewSet):
    model = Category
    chooser_per_page = 30
    # chooser_viewset_class = ChooserViewSet  # optional subclass
```

## Manual child ordering

Drag-and-drop reordering is available when `MP_Node.node_order_by` is **not** set (sibling order is path-based). If you set `node_order_by` on the model, reorder UI is omitted because inserts/moves already follow those fields.

## Development

```bash
python -Im pip install -U flit tox
python -Im flit build --format wheel
tox --installpkg ./dist/*.whl
```

Run a single environment:

```bash
tox -e py3.12-django4.2-wagtail6.3-sqlite
tox -e py3.13-django5.2-wagtail7.4-sqlite
```

Interactive test project (creates a superuser `admin` / `changeme`):

```bash
tox -e interactive
```

## License

MIT — see [LICENSE](LICENSE).
