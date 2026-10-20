"""Give the milestone/task foreign keys real ON DELETE actions at the database level."""

from django.db import migrations

from tracker.db_utils import fk_on_delete


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0002_milestone_task"),
    ]

    operations = [
        fk_on_delete("milestone", "project_id", "project", "project_id", "CASCADE"),
        fk_on_delete("task", "project_id", "project", "project_id", "CASCADE"),
        fk_on_delete("task", "milestone_id", "milestone", "milestone_id", "SET NULL"),
        fk_on_delete("task", "category_id", "category", "category_id", "SET NULL"),
    ]
