from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from treebeard.mp_tree import MP_Node

from wagtail_treebeard.viewsets import WagtailTreebeardSnippetViewSet


class NotTreebeard(MP_Node):
    class Meta:
        app_label = "testapp"


class WagtailTreebeardSnippetViewSetTests(SimpleTestCase):
    def test_rejects_model_without_treebeard_mixin(self):
        with self.assertRaises(ImproperlyConfigured):
            WagtailTreebeardSnippetViewSet(model=User)

    def test_rejects_mp_node_without_treebeard_mixin(self):
        with self.assertRaises(ImproperlyConfigured):
            WagtailTreebeardSnippetViewSet(model=NotTreebeard)
