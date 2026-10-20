"""Cascade task deletes into task_history at the database level."""

from django.db import migrations

from tracker.db_utils import fk_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0008_task_history"),
    ]

    operations = [
        fk_on_delete("task_history", "task_id", "task", "task_id", "CASCADE"),
    ]
