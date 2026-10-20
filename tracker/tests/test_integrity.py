"""
Database integrity tests. These run against PostgreSQL (the test database is
built by the real migrations, including the RunSQL triggers and views), so
they exercise the constraints and triggers themselves, not Python stand-ins.
"""

import datetime as dt

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from tracker.models import (
    Milestone,
    MilestoneProgress,
    Project,
    ProjectProgress,
    Task,
    TaskDependency,
    TaskHistory,
)

from .factories import START, make_milestone, make_project, make_task, make_user


def raw(sql, params=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() if cursor.description else None


class CheckConstraintTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project(self.user)

    def test_invalid_priority_rejected(self):
        with self.assertRaisesMessage(IntegrityError, "ck_task_priority"), transaction.atomic():
            make_task(self.project, priority="URGENT")

    def test_invalid_status_rejected(self):
        with self.assertRaisesMessage(IntegrityError, "ck_task_status"), transaction.atomic():
            make_task(self.project, status="DONE")

    def test_invalid_priority_rejected_in_raw_sql(self):
        with self.assertRaisesMessage(IntegrityError, "ck_task_priority"), transaction.atomic():
            raw("INSERT INTO task (project_id, title, priority) VALUES (%s, 'x', 'URGENT')", [self.project.pk])

    def test_project_deadline_before_start_rejected(self):
        with self.assertRaisesMessage(IntegrityError, "ck_project_deadline_after_start"), transaction.atomic():
            make_project(self.user, name="Backwards", start_date=START, deadline=START - dt.timedelta(days=1))

    def test_project_status_rejected(self):
        with self.assertRaisesMessage(IntegrityError, "ck_project_status"), transaction.atomic():
            make_project(self.user, name="Odd", status="ARCHIVED")

    def test_unique_project_name_per_owner(self):
        with self.assertRaisesMessage(IntegrityError, "uq_project_owner_name"), transaction.atomic():
            make_project(self.user, name="Apollo")
        # The same name is fine for a different owner.
        make_project(make_user("bob"), name="Apollo")

    def test_unique_milestone_name_per_project(self):
        make_milestone(self.project, name="Beta")
        with self.assertRaisesMessage(IntegrityError, "uq_milestone_project_name"), transaction.atomic():
            make_milestone(self.project, name="Beta")


class ForeignKeyTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project(self.user)

    def test_bad_foreign_key_rejected(self):
        # Django creates FKs as DEFERRABLE INITIALLY DEFERRED; make them
        # immediate so the violation is raised by this statement.
        with self.assertRaisesMessage(IntegrityError, "fk_task_project_id"), transaction.atomic():
            raw("SET CONSTRAINTS ALL IMMEDIATE")
            raw("INSERT INTO task (project_id, title) VALUES (987654321, 'orphan')")

    def test_delete_project_cascades_in_raw_sql(self):
        milestone = make_milestone(self.project)
        task = make_task(self.project, milestone=milestone)
        raw("DELETE FROM project WHERE project_id = %s", [self.project.pk])
        self.assertFalse(Milestone.objects.filter(pk=milestone.pk).exists())
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())
        self.assertFalse(TaskHistory.objects.filter(task_id=task.pk).exists())

    def test_delete_user_cascades_in_raw_sql(self):
        # Health-check issue 2: owner FKs must cascade in the database too.
        from tracker.models import Category, Tag

        Category.objects.create(owner=self.user, name="Ops")
        Tag.objects.create(owner=self.user, name="urgent")
        task = make_task(self.project)
        raw("SET CONSTRAINTS ALL IMMEDIATE")
        raw("DELETE FROM auth_user WHERE id = %s", [self.user.pk])
        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        self.assertFalse(Category.objects.filter(owner_id=self.user.pk).exists())
        self.assertFalse(Tag.objects.filter(owner_id=self.user.pk).exists())
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_delete_milestone_sets_task_milestone_null_in_raw_sql(self):
        milestone = make_milestone(self.project)
        task = make_task(self.project, milestone=milestone)
        raw("DELETE FROM milestone WHERE milestone_id = %s", [milestone.pk])
        task.refresh_from_db()
        self.assertIsNone(task.milestone_id)


class DependencyConstraintTests(TestCase):
    def setUp(self):
        project = make_project(make_user())
        self.a = make_task(project, "A")
        self.b = make_task(project, "B")

    def test_self_dependency_rejected(self):
        with self.assertRaisesMessage(IntegrityError, "ck_task_dependency_not_self"), transaction.atomic():
            TaskDependency.objects.create(task=self.a, depends_on_task=self.a)

    def test_duplicate_dependency_rejected(self):
        TaskDependency.objects.create(task=self.b, depends_on_task=self.a)
        with self.assertRaisesMessage(IntegrityError, "uq_task_dependency"), transaction.atomic():
            TaskDependency.objects.create(task=self.b, depends_on_task=self.a)


class TriggerTests(TestCase):
    def setUp(self):
        self.project = make_project(make_user())

    def history(self, task):
        return list(TaskHistory.objects.filter(task=task).values_list("old_status", "new_status"))

    def test_insert_logs_initial_status(self):
        task = make_task(self.project)
        self.assertEqual(self.history(task), [(None, "PENDING")])

    def test_status_change_creates_history_row(self):
        task = make_task(self.project)
        for status in ["IN_PROGRESS", "COMPLETED"]:
            task.status = status
            task.save()
        self.assertEqual(
            self.history(task),
            [(None, "PENDING"), ("PENDING", "IN_PROGRESS"), ("IN_PROGRESS", "COMPLETED")],
        )

    def test_update_without_status_change_logs_nothing(self):
        task = make_task(self.project)
        task.title = "Renamed"
        task.save()
        raw("UPDATE task SET status = status WHERE task_id = %s", [task.pk])
        self.assertEqual(len(self.history(task)), 1)

    def test_history_is_written_for_raw_sql_updates(self):
        task = make_task(self.project)
        raw("UPDATE task SET status = 'BLOCKED' WHERE task_id = %s", [task.pk])
        self.assertEqual(self.history(task)[-1], ("PENDING", "BLOCKED"))

    def test_completed_at_set_when_completed_and_cleared_when_reopened(self):
        task = make_task(self.project)
        self.assertIsNone(task.completed_at)

        before = timezone.now()
        task.status = Task.Status.COMPLETED
        task.save(update_fields=["status"])
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)
        self.assertGreaterEqual(task.completed_at, before - dt.timedelta(seconds=5))

        task.status = Task.Status.IN_PROGRESS
        task.save(update_fields=["status"])
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_completed_at_kept_on_unrelated_update(self):
        task = make_task(self.project, status=Task.Status.COMPLETED)
        task.refresh_from_db()
        stamp = task.completed_at
        self.assertIsNotNone(stamp)  # INSERT as COMPLETED is stamped too
        raw("UPDATE task SET title = 'renamed' WHERE task_id = %s", [task.pk])
        task.refresh_from_db()
        self.assertEqual(task.completed_at, stamp)


class TransactionTests(TestCase):
    def setUp(self):
        self.user = make_user()

    def test_rollback_leaves_no_rows(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                project = make_project(self.user, name="Doomed")
                make_milestone(project, "Phase 1")
                make_milestone(project, "Phase 2")
                make_task(project, priority="URGENT")  # violates ck_task_priority
        self.assertFalse(Project.objects.filter(name="Doomed").exists())
        self.assertFalse(Milestone.objects.filter(name__in=["Phase 1", "Phase 2"]).exists())

    def test_commit_keeps_all_rows(self):
        with transaction.atomic():
            project = make_project(self.user, name="Kept")
            make_milestone(project, "Phase 1")
            make_task(project, priority="HIGH")
        self.assertEqual(Project.objects.get(name="Kept").milestones.count(), 1)
        self.assertEqual(Project.objects.get(name="Kept").tasks.count(), 1)


class ViewTests(TestCase):
    """v_project_progress / v_milestone_progress must match a manual count."""

    def setUp(self):
        self.user = make_user()
        self.project = make_project(self.user)
        self.empty = make_project(self.user, name="Empty")
        self.m1 = make_milestone(self.project, "M1")
        self.m2 = make_milestone(self.project, "M2")
        today = timezone.localdate()
        specs = [
            ("COMPLETED", self.m1, today - dt.timedelta(days=3)),  # completed, past deadline: not overdue
            ("COMPLETED", self.m1, None),
            ("PENDING", self.m1, today - dt.timedelta(days=1)),    # overdue
            ("IN_PROGRESS", self.m2, today - dt.timedelta(days=9)),  # overdue
            ("BLOCKED", self.m2, today + dt.timedelta(days=5)),
            ("PENDING", None, None),
            ("COMPLETED", None, today),
        ]
        for i, (status, milestone, deadline) in enumerate(specs):
            make_task(self.project, f"T{i}", status=status, milestone=milestone, deadline=deadline)

    def manual(self, tasks):
        tasks = list(tasks)
        today = timezone.localdate()
        total = len(tasks)
        done = sum(t.status == "COMPLETED" for t in tasks)
        overdue = sum(t.status != "COMPLETED" and t.deadline is not None and t.deadline < today for t in tasks)
        pct = round(100 * done / total, 1) if total else 0
        return total, done, overdue, pct

    def test_project_progress_matches_manual_count(self):
        row = ProjectProgress.objects.get(project=self.project)
        total, done, overdue, pct = self.manual(self.project.tasks.all())
        self.assertEqual((row.total_tasks, row.completed_tasks, row.overdue_tasks), (total, done, overdue))
        self.assertEqual(float(row.completion_pct), pct)
        self.assertEqual((total, done, overdue, pct), (7, 3, 2, 42.9))

    def test_project_without_tasks_is_zero_not_null(self):
        row = ProjectProgress.objects.get(project=self.empty)
        self.assertEqual((row.total_tasks, row.completed_tasks, float(row.completion_pct)), (0, 0, 0.0))

    def test_milestone_progress_matches_manual_count(self):
        for milestone in (self.m1, self.m2):
            row = MilestoneProgress.objects.get(milestone=milestone)
            total, done, _, pct = self.manual(milestone.tasks.all())
            self.assertEqual((row.total_tasks, row.completed_tasks), (total, done))
            self.assertEqual(float(row.completion_pct), pct)

    def test_view_updates_after_status_change(self):
        task = self.project.tasks.get(title="T2")
        task.status = Task.Status.COMPLETED
        task.save(update_fields=["status"])
        row = ProjectProgress.objects.get(project=self.project)
        self.assertEqual((row.completed_tasks, row.overdue_tasks), (4, 1))
