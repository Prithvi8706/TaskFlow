"""
Run the analytical queries from sql/queries.sql for the Analytics page.

The file is the single source of truth: it is parsed into blocks headed by
`-- [Qn] Title`, and the psql variables `:owner_id` / `:task_id` are turned
into psycopg named parameters, so values are always bound, never pasted in.
"""

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

QUERIES_FILE = Path(settings.BASE_DIR) / "sql" / "queries.sql"

HEADER = re.compile(r"^-- \[Q(\d+)\] (.+)$")
PSQL_VAR = re.compile(r"(?<!:):(owner_id|task_id)\b")


@dataclass
class Query:
    number: int
    title: str
    answers: str = ""
    concepts: list = field(default_factory=list)
    sql: str = ""

    @property
    def uses_task(self):
        return ":task_id" in self.sql

    @property
    def bound_sql(self):
        return PSQL_VAR.sub(r"%(\1)s", self.sql)


@lru_cache(maxsize=1)
def load_queries():
    queries, current, body = [], None, []

    def finish():
        if current:
            current.sql = "\n".join(body).strip().rstrip(";").strip()
            queries.append(current)

    for line in QUERIES_FILE.read_text(encoding="utf-8").splitlines():
        match = HEADER.match(line)
        if match:
            finish()
            current, body = Query(int(match.group(1)), match.group(2).strip()), []
        elif current is None:
            continue  # file preamble and psql \set lines
        elif line.startswith("-- Answers:") and not body:
            current.answers = line.split(":", 1)[1].strip()
        elif line.startswith("-- Concepts:") and not body:
            current.concepts = [c.strip() for c in line.split(":", 1)[1].split(",") if c.strip()]
        else:
            body.append(line)
    finish()
    return queries


@dataclass
class QueryResult:
    query: Query
    columns: list
    rows: list


def run_queries(user, task_id):
    """Execute every query read-only for `user`; returns a list of QueryResult."""
    params = {"owner_id": user.pk, "task_id": task_id}
    results = []
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY")
        cursor.execute("SET LOCAL statement_timeout = '5s'")
        for query in load_queries():
            cursor.execute(query.bound_sql, params)
            columns = [col.name for col in cursor.description]
            rows = [[_display(value) for value in row] for row in cursor.fetchall()]
            results.append(QueryResult(query, columns, rows))
    return results


def _display(value):
    if value is None:
        return "—"
    if isinstance(value, dt.datetime):
        return timezone.localtime(value).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value
