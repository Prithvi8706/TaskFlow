# TaskFlow

A database-driven project and task manager, built as a DBMS course project.
Django handles the UI. The interesting parts live in **PostgreSQL**: CHECK and
UNIQUE constraints, real `ON DELETE` actions, two triggers, two views, a
recursive CTE and transaction examples, all visible from the app.

- **Stack:** Python 3.11+, Django 5.1, PostgreSQL 15+ (developed on 16), psycopg 3, Chart.js 4 (CDN), plain HTML/CSS
- **Docs:** [ER diagram and relational schema](docs/ER.md) · [Normalization to 3NF](docs/normalization.md)
- **SQL:** [`sql/triggers.sql`](sql/triggers.sql) · [`sql/views.sql`](sql/views.sql) · [`sql/queries.sql`](sql/queries.sql) · [`sql/transactions.sql`](sql/transactions.sql)

## Features

| Area | What you get |
|---|---|
| Auth | Register, sign in, sign out. All data is scoped to the signed-in user. |
| Projects | List, create (with initial milestones, in one transaction), edit, delete, and a detail page with progress from `v_project_progress`. |
| Milestones | CRUD inside a project; progress from `v_milestone_progress`. |
| Tasks | CRUD with validation, categories, tags (M:N through `task_tag`), prerequisites (recursive M:N with cycle detection), a blocked indicator, quick status change, and a status-history timeline written by a trigger. |
| Find | Search, filter by status / priority / project / category / tag, sort by deadline / priority / created. CSV export of exactly the filtered list. |
| Dashboard | KPI cards, tasks-by-status doughnut, completion-per-project bar chart, project progress and overdue list. Every number comes from a query. |
| Analytics | Runs the 13 queries in `sql/queries.sql` live (read-only transaction, bound parameters), each with its result table and SQL. |
| Polish | Dark mode, responsive layout with a mobile drawer, flash messages, empty states, confirm-before-delete. |

## Setup from a fresh clone

You need Python 3.11+, Git and either Docker or a local PostgreSQL 15+.

**1. Start PostgreSQL.** With Docker:

```bash
docker run -d --name taskflow-db --restart unless-stopped -e POSTGRES_USER=taskflow -e POSTGRES_PASSWORD=taskflow_dev -e POSTGRES_DB=taskflow -p 5432:5432 -v taskflow_pgdata:/var/lib/postgresql/data postgres:16
```

With a local install instead, create a role and database to match `.env`.
The role needs `CREATEDB` so `manage.py test` can create its test database.

**2. Create the virtualenv and install dependencies.**

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

(On macOS / Linux use `.venv/bin/python` in this and the following commands.)

**3. Configure the environment.** Copy `.env.example` to `.env` and set
`DJANGO_SECRET_KEY`. The database values already match the Docker command
above.

```bash
cp .env.example .env
```

**4. Create the schema.** The migrations also install the triggers and views
from `sql/`.

```bash
.venv/Scripts/python manage.py migrate
```

**5. Load the demo data.** This gives you 2 users, 4 projects, 12 milestones and
60 tasks with tags, dependencies, overdue work and trigger-written history. It
uses a fixed random seed, so every run produces the same data, with dates
relative to today. Re-running it wipes and reloads the demo users only.

```bash
.venv/Scripts/python manage.py seed_demo
```

**6. Run the app**, then open http://localhost:8000. Sign in as **`demo` /
`taskflow-demo`**; a second user, `alex`, has the same password.

```bash
.venv/Scripts/python manage.py runserver
```

### Running the tests

```bash
.venv/Scripts/python manage.py test
```

The 38 tests run against a real PostgreSQL test database built by the same
migrations. They cover: invalid priority, status and deadline rejected by
CHECK constraints; a bad foreign key rejected; self-dependency and duplicate
dependency rejected; cascade and set-null deletes issued in raw SQL; a history
row per status change, and none for a no-op update; `completed_at` set, kept
and cleared; rollback leaving no rows; view numbers matching a manual count;
cycle detection; per-user scoping; atomic project creation; all 13 analytics
queries; CSV export; and seed reproducibility.

Last run:

```
Found 38 test(s).
System check identified no issues (0 silenced).
......................................
----------------------------------------------------------------------
Ran 38 tests in 18.803s

OK
```

### Running the SQL files by hand

```bash
docker exec -i taskflow-db psql -U taskflow -d taskflow < sql/queries.sql
```

```bash
docker exec -i taskflow-db psql -U taskflow -d taskflow < sql/transactions.sql
```

`queries.sql` runs every query for the `demo` user (`\set owner_id`, `\set task_id`).
`transactions.sql` cleans up after itself, but Example 1 deliberately leaves
its committed project behind. Run `seed_demo` again for a clean dashboard.

## Project layout

```
config/                 settings (reads .env), root URLs
accounts/               registration, login, logout
tracker/
  models.py             tables + unmanaged models over the two views
  forms.py              validation, incl. DFS cycle check for dependencies
  views.py              pages, quick status, CSV export, dashboard
  analytics.py          parses sql/queries.sql and runs it read-only
  db_utils.py           helper giving FKs real ON DELETE actions
  migrations/           schema + RunSQL for sql/triggers.sql and sql/views.sql
  management/commands/seed_demo.py
  tests/                integrity + application tests
sql/                    triggers, views, 13 queries, transaction examples
docs/                   ER diagram, relational schema, normalization
templates/, static/     HTML templates, CSS tokens (light/dark), small JS
```

## Database design at a glance

- **Tables:** `category`, `project`, `milestone`, `task`, `tag`, `task_tag`,
  `task_dependency`, `task_history` (plus Django's `auth_user`). Every table has
  an explicit `db_table` and a readable primary-key name (`task.task_id`).
- **Relationships:** project 1:N task, task 1:N task_history, task M:N tag via
  `task_tag`, task recursive M:N task via `task_dependency`. Details are in
  [docs/ER.md](docs/ER.md).
- **Constraints:** `UNIQUE(owner_id, name)` on category, project and tag;
  `UNIQUE(project_id, name)` on milestone; `CHECK deadline >= start_date`; CHECK
  lists for every status and priority; `CHECK task_id <> depends_on_task_id`;
  `UNIQUE(task_id, tag_id)` and `UNIQUE(task_id, depends_on_task_id)`.
- **Cycle prevention:** a CHECK can only see one row, so longer cycles
  (A → B → C → A) are caught by a depth-first search in
  `TaskDependencyForm.clean()`.
- **Triggers:** `trg_task_status_history` is the only writer of `task_history`.
  `trg_task_completed_at` maintains `completed_at`.
- **Views:** `v_project_progress` and `v_milestone_progress`, mapped to
  `managed = False` models and used by the dashboard and project pages.
- **Transactions:** "create project with milestones" runs inside
  `transaction.atomic()`. `sql/transactions.sql` shows COMMIT vs ROLLBACK in
  psql.

## Viva demo script

Run `seed_demo` first so the numbers below match.

1. **Real KPIs and charts.** Sign in as `demo` / `taskflow-demo`. The dashboard
   shows 2 active projects, 21 of 45 tasks completed (46.7%), 9 in progress and
   6 overdue. The doughnut and bar chart are drawn from the same queries; the
   progress table is read from view `v_project_progress`.
2. **Atomic project creation.** Projects → New project. Fill in the fields and
   put `Design`, `Build` and `Launch` on separate lines under *Initial
   milestones*. The project and its three milestones are created in one
   `transaction.atomic()` block. A listed duplicate such as `Build` / `build`
   is rejected before anything is written.
3. **Task with tags and a prerequisite.** In the new project click *Add task*,
   tick a couple of tags and save. On the task page use *Add prerequisite* to
   pick another task in the project. The task now shows "Blocked", and the
   *Completed* button is disabled until the prerequisite is done.
4. **Self-dependency rejected.** In *Add prerequisite*, pick the task itself:
   "A task cannot depend on itself." The `CHECK (task_id <> depends_on_task_id)`
   constraint backs this up in the database.
5. **Cycle rejected.** Make B depend on A and C depend on B, then try A depends
   on C: "That would create a cycle: A → C → B → A." This is the DFS in the
   form's `clean()`.
6. **Trigger: status history.** On a task, click *In progress*, then
   *Completed*. The *Status history* timeline shows `Created as Pending →
   In progress → Completed` with timestamps. Those rows were inserted by
   `trg_task_status_history`, not by Django.
7. **Trigger: completed_at.** The *Completed* field in the task details now has
   a timestamp ("set by trigger"). Move the task back to *In progress* and it
   clears.
8. **View updates.** Back on the dashboard or project page, the completion
   percentage and counts have changed. `v_project_progress` is recomputed on
   every read, so it cannot drift.
9. **Analytics.** Open Analytics and walk through a few queries:
   - Q2 (CASE + aggregates),
   - Q7 (WHERE vs HAVING),
   - Q10 (nested subquery that keeps ties; Data Warehouse and Website are tied
     on 3 overdue),
   - Q13 (WITH RECURSIVE). For "Colour and type tokens" it walks four levels
     back to "Stakeholder interviews".

   *Show SQL* reveals each query exactly as it is written in `sql/queries.sql`.
   Changing the task picker reruns Q8 and Q13.
10. **COMMIT vs ROLLBACK.** In a terminal, run
    `docker exec -i taskflow-db psql -U taskflow -d taskflow < sql/transactions.sql`.
    Example 1 commits a project, two milestones and a task together. Example 2
    inserts a project and milestones, fails on `priority = 'URGENT'`
    (`ck_task_priority`), and after `ROLLBACK` the counts are 0.

## Sample query output

These are real outputs from `sql/queries.sql` for the `demo` user right after
`seed_demo`, captured on 2026-10-20. Overdue counts, `days_overdue` and
timestamps depend on the day you run it; the rest is fixed by the seed.

**Q1. Projects with total and completed task counts** (JOIN, GROUP BY)

```
 project_id |         project          | status  | total_tasks | completed_tasks
------------+--------------------------+---------+-------------+-----------------
         36 | Data Warehouse Migration | ON_HOLD |          15 |               4
         35 | Mobile App Launch        | ACTIVE  |          15 |               8
         34 | Website Redesign         | ACTIVE  |          15 |               9
```

**Q2. Completion percentage per project** (CASE, aggregate)

```
         project          | total_tasks | completed_tasks | completion_pct |    stage
--------------------------+-------------+-----------------+----------------+-------------
 Website Redesign         |          15 |               9 |           60.0 | Underway
 Mobile App Launch        |          15 |               8 |           53.3 | Underway
 Data Warehouse Migration |          15 |               4 |           26.7 | Early stage
```

**Q3. Overdue incomplete tasks** (date filtering)

```
 task_id |           title            |         project          | priority |   status    |  deadline  | days_overdue
---------+----------------------------+--------------------------+----------+-------------+------------+--------------
     214 | Colour and type tokens     | Website Redesign         | MEDIUM   | IN_PROGRESS | 2026-10-01 |           19
     239 | Inventory existing reports | Data Warehouse Migration | MEDIUM   | PENDING     | 2026-10-05 |           15
     252 | Runbook for on-call        | Data Warehouse Migration | MEDIUM   | BLOCKED     | 2026-10-07 |           13
     222 | Write launch checklist     | Website Redesign         | LOW      | IN_PROGRESS | 2026-10-08 |           12
     251 | Decommission old replica   | Data Warehouse Migration | HIGH     | PENDING     | 2026-10-18 |            2
     220 | Responsive layout pass     | Website Redesign         | HIGH     | PENDING     | 2026-10-19 |            1
```

**Q4. Task counts by status and priority** (GROUP BY two columns)

```
   status    | priority | tasks
-------------+----------+-------
 PENDING     | HIGH     |     5
 PENDING     | MEDIUM   |     4
 IN_PROGRESS | HIGH     |     3
 IN_PROGRESS | MEDIUM   |     3
 IN_PROGRESS | LOW      |     3
 BLOCKED     | MEDIUM   |     3
 BLOCKED     | LOW      |     3
 COMPLETED   | HIGH     |     4
 COMPLETED   | MEDIUM   |     9
 COMPLETED   | LOW      |     8
```

**Q5. Categories with the most tasks** (ORDER BY, LIMIT)

```
 category | tasks
----------+-------
 Backend  |    10
 DevOps   |     8
 QA       |     8
 Docs     |     7
 Frontend |     7
```

**Q6. Milestones with completion percentage** (uses `v_milestone_progress`)

```
         project          |       milestone        |  deadline  |   status    | total_tasks | completed_tasks | completion_pct
--------------------------+------------------------+------------+-------------+-------------+-----------------+----------------
 Data Warehouse Migration | Assessment             | 2026-10-25 | IN_PROGRESS |           5 |               4 |           80.0
 Data Warehouse Migration | Pipeline build         | 2026-12-14 | IN_PROGRESS |           4 |               0 |            0.0
 Data Warehouse Migration | Cut-over               | 2027-02-02 | IN_PROGRESS |           4 |               0 |            0.0
 Mobile App Launch        | MVP features           | 2026-09-30 | COMPLETED   |           5 |               5 |          100.0
 Mobile App Launch        | Beta programme         | 2026-11-09 | IN_PROGRESS |           4 |               3 |           75.0
 Mobile App Launch        | Store release          | 2026-12-19 | IN_PROGRESS |           4 |               0 |            0.0
 Website Redesign         | Discovery & wireframes | 2026-09-17 | COMPLETED   |           5 |               5 |          100.0
 Website Redesign         | Design system          | 2026-11-02 | IN_PROGRESS |           4 |               2 |           50.0
 Website Redesign         | Build & launch         | 2026-12-19 | IN_PROGRESS |           4 |               1 |           25.0
```

**Q7. Projects with more than five incomplete tasks** (HAVING)

```
         project          | incomplete_tasks
--------------------------+------------------
 Data Warehouse Migration |               11
 Mobile App Launch        |                7
 Website Redesign         |                6
```

**Q8. Status history of a task in chronological order** (trigger-written rows)

```
         title          | old_status | new_status  |          changed_at
------------------------+------------+-------------+-------------------------------
 Colour and type tokens |            | PENDING     | 2026-10-20 03:57:57.765571+00
 Colour and type tokens | PENDING    | IN_PROGRESS | 2026-10-20 03:57:57.784103+00
```

**Q9. Tasks whose prerequisites are not yet completed** (EXISTS subquery)

```
         title          |         project          | status  |        waiting_on
------------------------+--------------------------+---------+--------------------------
 Runbook for on-call    | Data Warehouse Migration | BLOCKED | Load testing
 Train analysts         | Data Warehouse Migration | BLOCKED | Access control and roles
 CI pipeline for builds | Mobile App Launch        | BLOCKED | Performance profiling
 Privacy policy update  | Mobile App Launch        | BLOCKED | App store screenshots
 Submit to app stores   | Mobile App Launch        | BLOCKED | App store screenshots
```

**Q10. Project with the most overdue tasks** (nested subquery; ties kept)

```
         project          | overdue_tasks
--------------------------+---------------
 Data Warehouse Migration |             3
 Website Redesign         |             3
```

**Q11. Average days taken to complete a task** (date arithmetic, ROLLUP)

```
         project          | completed_tasks | avg_days | fastest_days | slowest_days
--------------------------+-----------------+----------+--------------+--------------
 Website Redesign         |               9 |     67.4 |           46 |           79
 Mobile App Launch        |               8 |     30.6 |            1 |           57
 Data Warehouse Migration |               4 |     27.9 |           18 |           41
 All projects             |              21 |     45.8 |            1 |           79
```

**Q12. Projects above the overall average completion** (nested subquery)

```
      project      | completion_pct | average_pct
-------------------+----------------+-------------
 Website Redesign  |           60.0 |        46.7
 Mobile App Launch |           53.3 |        46.7
```

**Q13. Full prerequisite chain of a task** (WITH RECURSIVE)

```
 depth |            title             |  status   |                    via
-------+------------------------------+-----------+--------------------------------------------------------------
     1 | Choose headless CMS          | COMPLETED | Colour and type tokens → Choose headless CMS
     2 | Draft sitemap                | COMPLETED | Colour and type tokens → Choose headless CMS → Draft sitemap
     2 | Low-fidelity wireframes      | COMPLETED | Colour and type tokens → Choose headless CMS → Low-fidelity wireframes
     3 | Audit current site analytics | COMPLETED | … → Draft sitemap → Audit current site analytics
     4 | Stakeholder interviews       | COMPLETED | … → Audit current site analytics → Stakeholder interviews
```

### `sql/transactions.sql` output

```
=== Example 1: COMMIT ===
BEGIN
INSERT 0 1
INSERT 0 2
INSERT 0 1
COMMIT
After COMMIT the project, both milestones and the task exist:
       project       | milestones | tasks
---------------------+------------+-------
 Txn demo: committed |          2 |     1

=== Example 2: ROLLBACK ===
BEGIN
INSERT 0 1
INSERT 0 2
Inside the transaction the project is visible to this session:
         name          | status
-----------------------+---------
 Txn demo: rolled back | PLANNED

Now the failing INSERT (expect: violates check constraint "ck_task_priority"):
ERROR:  new row for relation "task" violates check constraint "ck_task_priority"
Any further statement is rejected (expect: current transaction is aborted):
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
After ROLLBACK nothing from Example 2 remains (expect 0 rows / 0 milestones):
 projects_left
---------------
             0

 milestones_left
-----------------
               0
```
