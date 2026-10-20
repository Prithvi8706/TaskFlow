# Normalization: from a flat task sheet to 3NF

This walks the TaskFlow schema from a single spreadsheet-style table to the
final relations in `docs/ER.md`, listing the functional dependencies (FDs) at
each step.

## 0. Unnormalised form (UNF): the "task sheet"

Imagine every user tracking work in one shared spreadsheet, one row per task:

| owner | owner_email | project | project_desc | proj_start | proj_deadline | proj_status | milestone | ms_deadline | ms_status | task_title | priority | status | task_deadline | created_at | completed_at | category | tags | prerequisites | status_log |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| demo | demo@… | Website Redesign | Rebuild the… | 2026-08-01 | 2026-12-19 | ACTIVE | Design system | 2026-11-02 | IN_PROGRESS | Colour and type tokens | MEDIUM | IN_PROGRESS | 2026-10-01 | 2026-08-20 | | Design | `feature, urgent` | `Choose headless CMS` | `PENDING@08-20, IN_PROGRESS@09-02` |
| demo | demo@… | Website Redesign | Rebuild the… | 2026-08-01 | 2026-12-19 | ACTIVE | Design system | 2026-11-02 | IN_PROGRESS | Choose headless CMS | HIGH | COMPLETED | 2026-09-10 | 2026-08-05 | 2026-09-09 | Backend | `research` | `Low-fidelity wireframes; Draft sitemap` | `PENDING@…, IN_PROGRESS@…, COMPLETED@…` |

Problems:

- **Non-atomic values.** `tags`, `prerequisites` and `status_log` hold lists.
  You cannot index, join or constrain an individual tag or status change.
- **Redundancy.** Owner email, every project column and every milestone column
  are repeated on every task row.
- **Update anomaly.** Renaming a project or moving a milestone deadline means
  editing many rows; miss one and the sheet contradicts itself.
- **Insertion anomaly.** A project with no tasks yet, or a tag nobody has used,
  cannot be recorded without a dummy task row.
- **Deletion anomaly.** Deleting the last task of a project loses the project's
  dates and description.

## 1. First normal form (1NF)

**Rule:** every attribute holds a single atomic value, and there are no
repeating groups.

The three multi-valued columns move into their own relations, each keyed by the
task's identifying attributes plus the repeated item. A task is identified by
(owner, project, task_title), because a title is unique within a project.

**TASK_1NF** (<u>owner, project, task_title</u>, owner_email, project_desc,
proj_start, proj_deadline, proj_status, milestone, ms_deadline, ms_status,
priority, status, task_deadline, created_at, completed_at, category)

**TASK_TAG_1NF** (<u>owner, project, task_title, tag</u>)

**TASK_PREREQ_1NF** (<u>owner, project, task_title, prereq_title</u>)

**TASK_STATUS_LOG_1NF** (<u>owner, project, task_title, changed_at</u>, old_status, new_status)

Functional dependencies in TASK_1NF:

| # | FD | Kind |
|---|---|---|
| F1 | owner → owner_email | **partial** (depends on part of the key) |
| F2 | (owner, project) → project_desc, proj_start, proj_deadline, proj_status | **partial** |
| F3 | (owner, project, milestone) → ms_deadline, ms_status | **transitive** (via the non-key `milestone`) |
| F4 | (owner, project, task_title) → milestone, priority, status, task_deadline, created_at, completed_at, category | full |

Every value is now atomic, so the relation is in 1NF. F1 and F2 are partial
dependencies, though, so the redundancy and anomalies from step 0 are still
there.

## 2. Second normal form (2NF)

**Rule:** 1NF, and no non-key attribute depends on only *part* of a composite
key.

Remove the partial dependencies F1 and F2 by putting each determinant in its
own relation:

**USER** (<u>owner</u>, owner_email): from F1

**PROJECT** (<u>owner, project</u>, project_desc, proj_start, proj_deadline, proj_status): from F2

**TASK_2NF** (<u>owner, project, task_title</u>, milestone, ms_deadline, ms_status,
priority, status, task_deadline, created_at, completed_at, category)

The tag, prerequisite and status-log relations are unchanged. Their non-key
attributes (old_status, new_status) depend on the whole key: a status change
is identified by the task *and* the moment it happened.

Tags and categories also exist without tasks (the insertion anomaly from step
0), and tag names belong to an owner, so they get their own relation:

**TAG** (<u>owner, tag</u>)

**CATEGORY** (<u>owner, category</u>)

Now FDs F1 and F2 are each the key of their own relation. The project anomalies
are gone: a project with no tasks is one PROJECT row.

## 3. Third normal form (3NF)

**Rule:** 2NF, and no non-key attribute depends transitively on the key
through another non-key attribute.

TASK_2NF still contains F3:

(owner, project, task_title) → milestone → (ms_deadline, ms_status)

The milestone's deadline and status are facts about the *milestone*, not the
task, so they repeat on every task in that milestone. Moving a milestone
deadline is still a multi-row update. Split it out:

**MILESTONE** (<u>owner, project, milestone</u>, ms_deadline, ms_status)

**TASK_3NF** (<u>owner, project, task_title</u>, milestone, category, priority,
status, task_deadline, created_at, completed_at)

with (owner, project, milestone) referencing MILESTONE and (owner, category)
referencing CATEGORY.

FDs remaining in TASK_3NF: only F4, whose determinant is the key, so TASK_3NF
is in 3NF. Every other relation's non-key attributes depend only on its whole
key. The schema is in 3NF, and because every determinant is a candidate key it
is also in **BCNF**.

## 4. From 3NF relations to the implemented tables

The final step replaces the wide natural composite keys with surrogate keys,
**without losing the natural keys**, which stay as UNIQUE constraints:

| 3NF relation | Table | Surrogate PK | Natural key kept as |
|---|---|---|---|
| USER | `auth_user` | id | UNIQUE(username) |
| PROJECT | `project` | project_id | UNIQUE(owner_id, name) |
| MILESTONE | `milestone` | milestone_id | UNIQUE(project_id, name) |
| CATEGORY | `category` | category_id | UNIQUE(owner_id, name) |
| TAG | `tag` | tag_id | UNIQUE(owner_id, name) |
| TASK_3NF | `task` | task_id | (titles may repeat; identity is task_id) |
| TASK_TAG_1NF | `task_tag` | task_tag_id | UNIQUE(task_id, tag_id) |
| TASK_PREREQ_1NF | `task_dependency` | dependency_id | UNIQUE(task_id, depends_on_task_id) |
| TASK_STATUS_LOG_1NF | `task_history` | history_id | (task_id, changed_at) indexed |

Why surrogates: renaming a project or task then changes one row instead of
cascading through every referencing row. Foreign keys are also narrow
integers, which keeps joins and indexes small.

In the implementation, `task` drops the 3NF requirement that titles be unique
within a project; real projects do have two tasks called "Write tests". Its
identity is `task_id`.

## 5. Deliberate, controlled redundancy

Two things look redundant. Both are intentional and kept consistent by the
database, not by application code:

1. **`task.completed_at`** could be derived from `task_history` (the
   `changed_at` of the latest transition into COMPLETED). It is stored so the
   "average days to complete" query (Q11) does not scan history. Trigger
   `trg_task_completed_at` keeps it correct on every INSERT/UPDATE, including
   ones typed directly in psql.
2. **`v_project_progress` / `v_milestone_progress`** look like stored totals
   but are **views**. They are recomputed from `task` on every read, so they
   can never drift out of sync.

`project_id` on `task` is not redundant with `milestone.project_id`: a task can
exist without a milestone. When both are set, the application checks they
agree (`TaskForm.clean`).
