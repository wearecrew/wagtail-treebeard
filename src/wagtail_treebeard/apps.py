from django.apps import AppConfig


class WagtailTreebeardConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "wagtail_treebeard"

    def ready(self) -> None:
        from wagtail_treebeard import checks  # noqa: F401
        from wagtail_treebeard import wagtail_hooks  # noqa: F401
