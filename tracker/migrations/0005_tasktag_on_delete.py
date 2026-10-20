"""Cascade deletes from task and tag into the task_tag junction at the database level."""

from django.db import migrations

from tracker.db_utils import fk_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0004_tag_tasktag"),
    ]

    operations = [
        fk_on_delete("task_tag", "task_id", "task", "task_id", "CASCADE"),
        fk_on_delete("task_tag", "tag_id", "tag", "tag_id", "CASCADE"),
    ]
