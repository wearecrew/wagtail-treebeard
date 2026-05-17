from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("testapp", "0002_custom_permission_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="BreadcrumbGroup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=255)),
                ("internal_code", models.CharField(default="", max_length=50)),
            ],
        ),
        migrations.CreateModel(
            name="BreadcrumbRelatedTreeNode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("path", models.CharField(max_length=255, unique=True)),
                ("depth", models.PositiveIntegerField()),
                ("numchild", models.PositiveIntegerField(default=0)),
                ("name", models.CharField(max_length=255)),
                (
                    "group",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name="tree_nodes",
                        to="testapp.breadcrumbgroup",
                    ),
                ),
            ],
            options={
                "verbose_name": "breadcrumb related tree node",
                "verbose_name_plural": "breadcrumb related tree nodes",
                "permissions": [("add_root", "Can add root entry")],
            },
        ),
    ]
