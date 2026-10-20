"""Helpers used by migrations to express database-level behaviour Django 5.1 cannot."""

from django.db import migrations


def fk_on_delete(table, column, ref_table, ref_column, action):
    """
    Replace the foreign key Django created on `table.column` with a named one that
    carries a real ON DELETE action, so deletes issued in raw SQL behave the same
    way as deletes issued through the ORM.
    """
    name = f"fk_{table}_{column}"
    forward = f"""
        DO $$
        DECLARE c text;
        BEGIN
            SELECT con.conname INTO c
            FROM pg_constraint con
            JOIN pg_attribute att
              ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
            WHERE con.conrelid = '{table}'::regclass
              AND con.contype = 'f'
              AND att.attname = '{column}';
            IF c IS NOT NULL THEN
                EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', c);
            END IF;
        END $$;
        ALTER TABLE {table}
            ADD CONSTRAINT {name} FOREIGN KEY ({column})
            REFERENCES {ref_table} ({ref_column}) ON DELETE {action}
            DEFERRABLE INITIALLY DEFERRED;
    """
    reverse = f"""
        ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name};
        ALTER TABLE {table}
            ADD CONSTRAINT {name} FOREIGN KEY ({column})
            REFERENCES {ref_table} ({ref_column}) DEFERRABLE INITIALLY DEFERRED;
    """
    return migrations.RunSQL(forward, reverse)
