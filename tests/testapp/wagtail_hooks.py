from wagtail.snippets.models import register_snippet

from wagtail_treebeard.viewsets import WagtailTreebeardSnippetViewSet

from .models import (
    BreadcrumbRelatedTreeNode,
    CombinedCustomNode,
    PolicyRestrictedNode,
    TesterLockedNode,
    TreeNode,
)


class TreeNodeViewSet(WagtailTreebeardSnippetViewSet):
    model = TreeNode
    menu_label = "Tree nodes"
    icon = "folder"
    add_to_admin_menu = True
    form_fields = ["name"]


class PolicyRestrictedNodeViewSet(WagtailTreebeardSnippetViewSet):
    model = PolicyRestrictedNode
    menu_label = "Policy restricted"
    icon = "folder-open-inverse"


class TesterLockedNodeViewSet(WagtailTreebeardSnippetViewSet):
    model = TesterLockedNode
    menu_label = "Tester locked"
    icon = "lock"
    form_fields = ["name", "is_locked"]


class CombinedCustomNodeViewSet(WagtailTreebeardSnippetViewSet):
    model = CombinedCustomNode
    menu_label = "Combined custom"
    icon = "cog"


class BreadcrumbRelatedTreeNodeViewSet(WagtailTreebeardSnippetViewSet):
    model = BreadcrumbRelatedTreeNode
    menu_label = "Breadcrumb related"
    icon = "folder-open-1"
    form_fields = ["name", "group"]


register_snippet(TreeNode, viewset=TreeNodeViewSet)
register_snippet(PolicyRestrictedNode, viewset=PolicyRestrictedNodeViewSet)
register_snippet(TesterLockedNode, viewset=TesterLockedNodeViewSet)
register_snippet(CombinedCustomNode, viewset=CombinedCustomNodeViewSet)
register_snippet(BreadcrumbRelatedTreeNode, viewset=BreadcrumbRelatedTreeNodeViewSet)
