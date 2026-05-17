from enum import StrEnum


class ChooserMode(StrEnum):
    CHOOSE = "choose"
    PARENT_FOR_CREATE = "parent_for_create"
    PARENT_FOR_MOVE = "parent_for_move"


PRESERVED_CHOOSER_PARAMS = (
    "multiple",
    "parent_pk",
    "chooser_mode",
    "move_instance_pk",
)
