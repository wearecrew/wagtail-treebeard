# wagtail-treebeard

[![Lint](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/lint.yml/badge.svg?branch=main&event=push)](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/lint.yml?query=branch%3Amain+event%3Apush)
[![Test](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/test.yml/badge.svg?branch=main&event=push)](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/test.yml?query=branch%3Amain+event%3Apush)
[![Nightly Wagtail main](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/nightly.yml/badge.svg?branch=main)](https://github.com/wearecrew/wagtail-treebeard/actions/workflows/nightly.yml?query=branch%3Amain)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An add-on for managing treebeard `MP_Node`-based snippet models in Wagtail.

- [Changelog](CHANGELOG.md)
- [Contributing](CONTRIBUTING.md)

Requires **Wagtail 7.3+** (snippet reorder, `set_max_order`, and viewset URL helpers used by this package).

## Supported versions

- Python 3.12, 3.13, 3.14
- Django 5.2, 6.0 (see [Wagtail’s compatibility table](https://docs.wagtail.org/en/stable/releases/upgrading.html#compatible-django-python-versions) for each Wagtail release)
- **Minimum** Wagtail 7.3; **LTS** [7.4](https://docs.wagtail.org/en/stable/releases/7.4.html) (see the [release index](https://docs.wagtail.org/en/stable/releases/index.html))
- CI tests **7.3** and **7.4** on supported Django/Python pairs, plus **Wagtail `main`** nightly (see [package guidelines](https://github.com/wagtail/wagtail/blob/main/docs/contributing/package_guidelines.md))

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

Treebeard follows the same split as Wagtail pages: a **permission policy** answers “which nodes are valid parents?” across the admin, and a **permission tester** answers “what can this user do to *this* node?” for row actions and chooser rows.

### Default permission configuration

`TreebeardMixin` wires in:

| Attribute | Default class |
|-----------|---------------|
| `permission_policy_class` | `TreebeardModelPermissionPolicy` |
| `permission_tester_class` | `TreebeardPermissionTester` |

#### Django model permissions

`TreebeardModelPermissionPolicy` extends Wagtail’s `ModelPermissionPolicy`, so the usual snippet permissions apply:

| Permission | Typical use in treebeard admin |
|------------|--------------------------------|
| **add** | Create children under an allowed parent; required for any create flow |
| **change** | Edit, move, reorder children |
| **delete** | Delete leaf nodes (nodes with children are blocked in the UI) |

Placement checks call `user_has_permission()` for `add` or `change` before returning parent querysets.

#### Where valid parents come from

By default, any user with the right Django permission may choose **any** node as a parent:

- `instances_user_can_add_children_to(user)` — all nodes (used when creating a child: select-parent form, create chooser, POST validation).
- `instances_user_can_move_to(user, instance)` — same set, minus the node being moved and its current parent (used on the move form, move chooser search, and per-row move checks).

Override these querysets when only certain nodes should accept children or moves (see [Customising permissions](#customising-permissions)).

#### “Can add root entry” (`add_root`)

Each concrete `TreebeardMixin` subclass gets a custom permission on `Meta.permissions` by default:

- **Codename:** `add_root`
- **Label in admin:** “Can add root entry”

It is registered automatically unless you set `register_add_root_permission = False` on the model.

When `add_root` is present on the model, `user_can_add_root(user)` requires **both** `add` **and** `add_root`. That gates:

- **Create at root** — “Add to the root level” on the select-parent step, and the `add/root/` URL.
- **Move to root** — “Move to root level” on the move view (only for nodes that are not already roots).

If you disable the custom permission (`register_add_root_permission = False`), `user_can_add_root()` only checks `add`, so anyone who may add snippets may also add or promote nodes to the root.

Assign `add_root` in the Groups UI like any other permission. Users with `add` but not `add_root` can still create and move nodes **under existing parents**, but cannot create new roots or move nodes to the root level.

#### Per-node tester (default behaviour)

`node.permissions_for_user(user)` returns a `TreebeardPermissionTester` that combines Django permissions, the policy querysets, and optional model rules:

| Method | Meaning |
|--------|---------|
| `can_add_child()` | User has `add` and this node is in `instances_user_can_add_children_to` |
| `can_move_to(parent)` | User has `change` and `parent` is in `instances_user_can_move_to` for this node |
| `can_move()` | User has `change`, `node.can_move()` is true, and there is at least one move target (another parent **or** move-to-root when allowed) |
| `can_reorder_children()` | Manual ordering is enabled, user has `change`, and the node has children |

#### Domain rule on the model

Override `can_move()` on the model when a **specific instance** must not be moved at all (before choosing a target parent). The tester and move view both honour this. Use the policy/tester when the rule depends on the user or parent; use `can_move()` for instance state (e.g. a `locked` flag).

### Customising permissions

#### Permission policy vs permission tester

| | Permission policy | Permission tester |
|---|-------------------|-------------------|
| **Scope** | Whole model / user | One user + one node |
| **Returns** | Querysets, booleans like `user_can_add_root` | `can_add_child`, `can_move`, etc. |
| **Used for** | Parent pickers, search results, form field querysets, POST checks | Index row actions, chooser row buttons, “can I move *this* row?” |
| **Override when** | Valid parents depend on node type, flags, or collections | Actions depend on node state, workflow, or logic not expressible as a queryset |

Keep placement rules in the **policy** so choosers, forms, and POST validation stay aligned. Use the **tester** for per-row UI or when you need to combine policy results with extra checks. Call `super()` in tester methods so Django and policy rules still apply.

Set classes on the model:

```python
class Category(TreebeardMixin, MP_Node):
    permission_policy_class = CategoryPermissionPolicy
    permission_tester_class = CategoryPermissionTester
```

#### Override the permission policy

Subclass `TreebeardModelPermissionPolicy` and restrict which nodes appear as valid parents.

**Example — only nodes flagged to accept children / moves:**

```python
from wagtail_treebeard.permission_policy import TreebeardModelPermissionPolicy


class CategoryPermissionPolicy(TreebeardModelPermissionPolicy):
    def instances_user_can_add_children_to(self, user):
        return (
            super()
            .instances_user_can_add_children_to(user)
            .filter(accept_children=True)
        )

    def instances_user_can_move_to(self, user, instance=None):
        if not self.user_has_permission(user, "change"):
            return self.model._default_manager.none()
        qs = self.model._default_manager.filter(accept_moves_as_target=True).order_by("path")
        if instance is not None:
            qs = qs.exclude(pk=instance.pk)
            if instance.depth > 1:
                qs = qs.exclude(path=instance.path[: -self.model.steplen])
        return qs


class Category(TreebeardMixin, MP_Node):
    permission_policy_class = CategoryPermissionPolicy
    accept_children = models.BooleanField(default=True)
    accept_moves_as_target = models.BooleanField(default=True)
    # ...
```

When overriding `instances_user_can_move_to`, either call `super()` (so add-child rules still apply) or reimplement the exclusions for `instance` and its current parent, as above.

**Example — disable separate root permission:**

```python
class Category(TreebeardMixin, MP_Node):
    register_add_root_permission = False  # root create/move-to-root needs only `add`
```

#### Override the permission tester

Subclass `TreebeardPermissionTester` when actions on a **specific node** should differ from what the policy queryset implies.

**Example — locked nodes cannot gain children, move, or be reordered:**

```python
from wagtail_treebeard.permission_tester import TreebeardPermissionTester


class CategoryPermissionTester(TreebeardPermissionTester):
    def can_add_child(self):
        if self.node.is_locked:
            return False
        return super().can_add_child()

    def can_move(self):
        if self.node.is_locked:
            return False
        return super().can_move()

    def can_reorder_children(self):
        if self.node.is_locked:
            return False
        return super().can_reorder_children()


class Category(TreebeardMixin, MP_Node):
    permission_tester_class = CategoryPermissionTester
    is_locked = models.BooleanField(default=False)

    def can_move(self):
        return not self.is_locked  # domain rule: locked rows never move
```

You can combine both: a policy that limits valid parents globally, plus a tester (and/or `can_move()`) for per-instance flags. The test app’s `PolicyRestrictedNode` and `TesterLockedNode` models demonstrate each approach separately.

## Chooser

`WagtailTreebeardSnippetViewSet` registers a tree-aware snippet chooser (`TreebeardModelChooser`) for use in panels and StreamField blocks—the same integration point as Wagtail’s stock snippet chooser, but with explorer-style navigation:

- **Browse** — one tree level at a time; use the row action to descend into children (like the page chooser).
- **Search** — when your viewset defines search fields (as for a normal snippet chooser), the search tab returns a flat list of matches across the tree.

Configure page size on the viewset (default **50** for treebeard snippets, vs **10** on stock `SnippetViewSet`):

```python
class CategoryViewSet(WagtailTreebeardSnippetViewSet):
    model = Category
    search_fields = ["name"]  # enables the chooser search tab
    chooser_per_page = 30
    # chooser_viewset_class = ChooserViewSet  # optional subclass
```

## Manual child ordering

Drag-and-drop reordering is available when `MP_Node.node_order_by` is **not** set (sibling order is path-based). If you set `node_order_by` on the model, reorder UI is omitted because inserts/moves already follow those fields.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md). Quick start:

```bash
python -Im pip install -U flit tox pre-commit
pre-commit install
make test-ci          # full matrix
make test-future      # Wagtail main
```

Single environment:

```bash
tox -e py3.12-django5.2-wagtail74
tox -e py3.13-django6.0-wagtail74
```

Interactive test project (superuser `admin` / `changeme`):

```bash
make interactive
```

## License

MIT — see [LICENSE](LICENSE).
