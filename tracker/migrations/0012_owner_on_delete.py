"""Cascade user deletes into the tables they own at the database level."""

from django.db import migrations

from tracker.db_utils import fk_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0011_progress_views"),
    ]

    operations = [
        fk_on_delete("category", "owner_id", "auth_user", "id", "CASCADE"),
        fk_on_delete("project", "owner_id", "auth_user", "id", "CASCADE"),
        fk_on_delete("tag", "owner_id", "auth_user", "id", "CASCADE"),
    ]
