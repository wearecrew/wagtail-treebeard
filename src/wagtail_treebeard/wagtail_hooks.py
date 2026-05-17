from wagtail import hooks

from wagtail_treebeard.bulk_actions import TreebeardDeleteBulkAction


hooks.register("register_bulk_action", TreebeardDeleteBulkAction, order=100)
