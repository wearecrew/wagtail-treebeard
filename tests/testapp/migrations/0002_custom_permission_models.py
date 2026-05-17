from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("testapp", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PolicyRestrictedNode",
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
                ("accept_children", models.BooleanField(default=True)),
                ("accept_moves_as_target", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "policy restricted node",
                "verbose_name_plural": "policy restricted nodes",
                "permissions": [("add_root", "Can add root entry")],
            },
        ),
        migrations.CreateModel(
            name="TesterLockedNode",
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
                ("is_locked", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "tester locked node",
                "verbose_name_plural": "tester locked nodes",
                "permissions": [("add_root", "Can add root entry")],
            },
        ),
        migrations.CreateModel(
            name="CombinedCustomNode",
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
                ("accept_children", models.BooleanField(default=True)),
                ("accept_moves_as_target", models.BooleanField(default=True)),
                ("is_locked", models.BooleanField(default=False)),
            ],
            options={
                "verbose_name": "combined custom node",
                "verbose_name_plural": "combined custom nodes",
                "permissions": [("add_root", "Can add root entry")],
            },
        ),
    ]
