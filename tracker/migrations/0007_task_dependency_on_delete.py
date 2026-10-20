"""Cascade task deletes into task_dependency at the database level."""

from django.db import migrations

from tracker.db_utils import fk_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0006_task_dependency"),
    ]

    operations = [
        fk_on_delete("task_dependency", "task_id", "task", "task_id", "CASCADE"),
        fk_on_delete("task_dependency", "depends_on_task_id", "task", "task_id", "CASCADE"),
    ]
