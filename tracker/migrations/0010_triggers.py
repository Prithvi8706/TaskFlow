"""Install the PostgreSQL triggers defined in sql/triggers.sql."""

from pathlib import Path

from django.db import migrations

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"

DROP_TRIGGERS = """
    DROP TRIGGER IF EXISTS trg_task_status_history ON task;
    DROP TRIGGER IF EXISTS trg_task_completed_at ON task;
    DROP FUNCTION IF EXISTS fn_task_status_history();
    DROP FUNCTION IF EXISTS fn_task_completed_at();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("tracker", "0009_task_history_on_delete"),
    ]

    operations = [
        migrations.RunSQL((SQL_DIR / "triggers.sql").read_text(encoding="utf-8"), DROP_TRIGGERS),
    ]
