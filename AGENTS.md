# Agent guide: wagtail-treebeard

Wagtail **library** (not an application) for admin UX around django-treebeard **`MP_Node`** snippet models: browse-by-level index, parent-picked create, move, sibling reorder, choosers.

Repository: https://github.com/wearecrew/wagtail-treebeard

## Layout

| Path | Role |
|------|------|
| `src/wagtail_treebeard/models.py` | `TreebeardMixin` — permission classes, `permissions_for_user`, optional `add_root` Meta permission |
| `src/wagtail_treebeard/viewsets.py` | `WagtailTreebeardSnippetViewSet` — URL registration, wires view classes |
| `src/wagtail_treebeard/views.py` | Admin views (index, create, move, reorder children/roots, delete) |
| `src/wagtail_treebeard/forms.py` | Parent pickers, move form |
| `src/wagtail_treebeard/permission_policy.py` | Model-wide rules: valid parents, reorder gates, querysets |
| `src/wagtail_treebeard/permission_tester.py` | Per-node: `can_add_child`, `can_move`, `can_reorder_children` |
| `src/wagtail_treebeard/utils.py` | MP path helpers, **sibling reorder** (`_reorder_sibling_by_index`, `move_mp_*`, `apply_mp_*`) |
| `src/wagtail_treebeard/choosers/` | Snippet chooser browse/search for tree models |
| `tests/` | Django test project (`tests/manage.py`, `tests/testapp/`) — **all tests run here** |
| `tests/testapp/models.py` | `TreeNode`, locked/restrictive variants for integration tests |
| `justfile` | Local dev commands (`just`, `just test`, `just interactive`, …) |
| `tox.ini` | CI matrix; do not assume pytest at repo root |

## Domain invariants

### Move vs reorder

- **Move** — change parent (treebeard `MP_Node.move()` / placement policy). Uses `instances_user_can_move_to`, move view, chooser.
- **Reorder** — rewrite **sibling `path` order only** under a fixed parent (or among roots). Implemented in `utils.py` via batched path `UPDATE`s, **not** `MP_Node.move()`.

### Reorder permissions (default policy)

- **Children:** `change` on the **parent** + `parent.numchild >= 2`. Not per-child `change`.
- **Roots:** model-level `change` + at least two root nodes.
- Reorder UI lists **all** direct children (or all roots) via `changeable_siblings_queryset` — gated by parent/model `change`, not `instances_user_can_change` per sibling.
- Omitted when `MP_Node.node_order_by` is set (`model_supports_manual_ordering`).

### Policy vs tester

- **Policy** — querysets and booleans used by forms, choosers, POST checks, reorder views.
- **Tester** — per-row index/chooser actions; call `super()` when overriding.
- Keep placement rules in the **policy** so UI and POST stay aligned.

### Other UX rules

- **No bulk delete** on the snippet index (nodes with children cannot be deleted from row actions either).
- Treebeard fields `path`, `depth`, `numchild` are excluded from admin forms.
- Optional **`add_root`** Meta permission gates creating/moving to root (see README).

## Code style for agents

- **Imports at module top** — only inline imports to break real circular dependencies.
- **Prefer fewer, larger functions** over scattered one-off helpers when logic belongs together.
- Match existing naming and docstring level; avoid drive-by refactors or unrelated file edits.
- User-visible strings: `gettext_lazy` / `_()`.

## Development

Install [just](https://just.systems/man/en/packages.html) and [uv](https://docs.astral.sh/uv/). See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
just sync             # .venv: editable package + Wagtail + dev tools (for the editor)
just test             # single tox env (fast feedback; authoritative for CI)
just test-one tests.test_views.TreebeardAdminViewTests.test_foo
just test-ci          # full matrix before PR
just lint
just run              # test project via uv — http://localhost:8020/admin/ (admin / changeme)
just migrate          # after switching git branches (uv)
```

**Editor:** after `just sync`, use `.venv/bin/python` and `python.analysis.extraPaths`: `["src", "tests"]` (see `.vscode/settings.json.example`). Tox envs are not used by the language server.

Tests use Django’s runner via tox, not `pytest` from the repo root:

```bash
tox -e py3.13-django5.2-wagtail74
tox -e py3.13-django5.2-wagtail74 -- tests.test_utils.MpSiblingReorderTests
```

### Footguns

- **Branch switches:** migration warnings on `testapp` are common — run `just migrate` or tox with `--run-syncdb` in `commands_pre` (already in tox test envs).
- **`assertNumQueries` in `tests/test_utils.py`:** encodes the **single-index** reorder path (`_reorder_sibling_by_index`); do not route full-list drags through `apply_mp_sibling_order` without updating those tests.
- **Wagtail 7.3+** required (reorder APIs, viewset URL helpers).
- **Do not** reintroduce per-sibling `change` checks for reorder unless product requirements change — parent `change` + `numchild` is intentional.

## Adding behaviour

1. Policy/tester changes for permissions → `permission_policy.py` / `permission_tester.py` + `tests/test_permissions.py`.
2. Admin HTTP/views → `views.py` + `tests/test_views.py` (use `tests/testapp` models and `snippet_url` helpers).
3. Path/reorder mechanics → `utils.py` + `tests/test_utils.py` (prefer order/`numchild` assertions over brittle query counts unless testing the optimiser).
4. User-facing docs → `README.md`; dev workflow → `CONTRIBUTING.md` / this file.

## Releases

Version in `src/wagtail_treebeard/__version__.py`; user-facing notes in `CHANGELOG.md` under **Unreleased**.
