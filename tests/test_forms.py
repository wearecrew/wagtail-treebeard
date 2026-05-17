from django.forms.models import modelform_factory
from django.test import TestCase

from testapp.models import TreeNode
from wagtail_treebeard.forms import (
    ConfirmAddPositionForm,
    MoveForm,
    WagtailTreebeardAdminModelForm,
)


class WagtailTreebeardAdminModelFormTests(TestCase):
    def test_stores_parent_kwarg(self):
        parent = object()
        form_class = modelform_factory(
            TreeNode, form=WagtailTreebeardAdminModelForm, fields=["name"]
        )
        form = form_class(parent=parent)
        self.assertIs(form.parent, parent)


class ConfirmAddPositionFormTests(TestCase):
    def test_parent_field_uses_treebeard_chooser(self):
        form = ConfirmAddPositionForm(
            model=TreeNode, parent_queryset=TreeNode.objects.none()
        )
        widget = form.fields["parent"].widget
        self.assertEqual(widget.__class__.__name__, "TreebeardParentChooser")


class MoveFormTests(TestCase):
    def test_new_parent_field_uses_move_chooser(self):
        form = MoveForm(
            model=TreeNode,
            parent_queryset=TreeNode.objects.none(),
            move_instance_pk=1,
        )
        widget = form.fields["new_parent"].widget
        self.assertEqual(widget.__class__.__name__, "TreebeardMoveParentChooser")
