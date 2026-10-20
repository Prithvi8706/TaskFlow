"""Application-level tests: forms, ownership, atomic creation, analytics, export."""

import csv
import io
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from tracker.analytics import load_queries, run_queries
from tracker.forms import TaskDependencyForm, TaskForm
from tracker.models import Milestone, Project, Task, TaskDependency

from .factories import make_project, make_task, make_user


class DependencyFormTests(TestCase):
    def setUp(self):
        project = make_project(make_user())
        self.a, self.b, self.c = (make_task(project, t) for t in "ABC")

    def form(self, task, prereq):
        return TaskDependencyForm({"depends_on_task": prereq.pk}, task=task)

    def test_self_dependency_rejected_by_form(self):
        form = self.form(self.a, self.a)
        self.assertFalse(form.is_valid())
        self.assertIn("cannot depend on itself", str(form.errors))

    def test_cycle_rejected_by_form(self):
        TaskDependency.objects.create(task=self.b, depends_on_task=self.a)  # B needs A
        TaskDependency.objects.create(task=self.c, depends_on_task=self.b)  # C needs B
        form = self.form(self.a, self.c)  # A needs C would close the loop
        self.assertFalse(form.is_valid())
        self.assertIn("cycle", str(form.errors))
        self.assertIn("A → C → B → A", str(form.errors))

    def test_valid_dependency_saved(self):
        form = self.form(self.b, self.a)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertEqual(self.b.open_prerequisites(), [self.a])


class OwnershipAndStatusTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")
        self.project = make_project(self.alice)
        self.task = make_task(self.project, "Secret")
        self.client.force_login(self.bob)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get("/tasks/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_other_users_rows_are_404(self):
        for url in [f"/projects/{self.project.pk}/", f"/tasks/{self.task.pk}/", f"/tasks/{self.task.pk}/edit/"]:
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.client.post(f"/tasks/{self.task.pk}/status/", {"status": "COMPLETED"}).status_code, 404)

    def test_quick_status_blocked_by_open_prerequisite(self):
        self.client.force_login(self.alice)
        prereq = make_task(self.project, "First")
        TaskDependency.objects.create(task=self.task, depends_on_task=prereq)
        self.client.post(f"/tasks/{self.task.pk}/status/", {"status": "COMPLETED"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "PENDING")

        self.client.post(f"/tasks/{prereq.pk}/status/", {"status": "COMPLETED"})
        self.client.post(f"/tasks/{self.task.pk}/status/", {"status": "COMPLETED"})
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, "COMPLETED")
        self.assertIsNotNone(self.task.completed_at)


class AtomicProjectCreationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.data = {"name": "Launch", "status": "PLANNED", "start_date": "2026-01-01", "deadline": "2026-03-01"}

    def test_project_created_with_milestones(self):
        self.client.post("/projects/new/", {**self.data, "initial_milestones": "Design\nBuild\n\nShip"})
        project = Project.objects.get(name="Launch")
        self.assertEqual(sorted(project.milestones.values_list("name", flat=True)), ["Build", "Design", "Ship"])

    def test_failed_milestone_insert_rolls_back_project(self):
        with mock.patch.object(Milestone.objects, "bulk_create", side_effect=IntegrityError("boom")):
            with self.assertRaises(IntegrityError):
                self.client.post("/projects/new/", {**self.data, "initial_milestones": "Design"})
        self.assertFalse(Project.objects.filter(name="Launch").exists())


class AnalyticsTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.project = make_project(self.user)
        self.a = make_task(self.project, "A", status="COMPLETED")
        self.b = make_task(self.project, "B")
        self.c = make_task(self.project, "C")
        TaskDependency.objects.create(task=self.b, depends_on_task=self.a)
        TaskDependency.objects.create(task=self.c, depends_on_task=self.b)
        other = make_project(make_user("bob"), name="Bob's project")
        make_task(other, "Bob task")

    def test_file_has_thirteen_queries(self):
        queries = load_queries()
        self.assertEqual([q.number for q in queries], list(range(1, 14)))
        for q in queries:
            self.assertTrue(q.answers and q.concepts, q.number)
            self.assertNotIn(":owner_id", q.bound_sql)

    def test_all_queries_run_and_are_scoped_to_the_user(self):
        results = {r.query.number: r for r in run_queries(self.user, self.c.pk)}
        self.assertEqual(len(results), 13)
        self.assertEqual(results[1].rows[0][1], "Apollo")
        self.assertEqual(len(results[1].rows), 1)  # Bob's project is not visible
        flat = str([r.rows for r in results.values()])
        self.assertNotIn("Bob", flat)

    def test_recursive_chain_query(self):
        chain = next(r for r in run_queries(self.user, self.c.pk) if r.query.number == 13)
        self.assertEqual([(row[0], row[1]) for row in chain.rows], [(1, "B"), (2, "A")])

    def test_analytics_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/analytics/?task={self.c.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WITH RECURSIVE")


class ExportTests(TestCase):
    def test_csv_respects_filters(self):
        user = make_user()
        project = make_project(user)
        make_task(project, "Hot", priority="HIGH")
        make_task(project, "Cold", priority="LOW")
        self.client.force_login(user)
        response = self.client.get("/tasks/export.csv?priority=HIGH")
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertEqual([r[1] for r in rows[1:]], ["Hot"])


class SeedCommandTests(TestCase):
    def test_seed_demo_is_reproducible(self):
        call_command("seed_demo", stdout=io.StringIO())
        first = list(Task.objects.order_by("title").values_list("title", "status", "priority", "deadline"))
        call_command("seed_demo", stdout=io.StringIO())
        second = list(Task.objects.order_by("title").values_list("title", "status", "priority", "deadline"))
        self.assertEqual(len(first), 60)
        self.assertEqual(first, second)
        self.assertEqual(Project.objects.count(), 4)
        self.assertEqual(Milestone.objects.count(), 12)


class CrossProjectCycleTests(TestCase):
    """Health-check issue 1: links that span projects must not hide a cycle."""

    def setUp(self):
        self.user = make_user()
        self.p1 = make_project(self.user, name="P1")
        self.p2 = make_project(self.user, name="P2")
        self.x = make_task(self.p1, "X")
        self.y = make_task(self.p1, "Y")

    def test_moving_a_task_with_dependencies_to_another_project_is_rejected(self):
        TaskDependency.objects.create(task=self.y, depends_on_task=self.x)
        form = TaskForm(
            {"title": "Y", "project": self.p2.pk, "priority": "MEDIUM", "status": "PENDING"},
            instance=self.y,
            user=self.user,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("project", form.errors)

    def test_moving_a_task_without_dependencies_is_allowed(self):
        form = TaskForm(
            {"title": "Y", "project": self.p2.pk, "priority": "MEDIUM", "status": "PENDING"},
            instance=self.y,
            user=self.user,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_cycle_through_a_cross_project_link_is_detected(self):
        z = make_task(self.p2, "Z")
        # Pre-existing links that cross projects (e.g. created before the move rule).
        TaskDependency.objects.create(task=self.y, depends_on_task=z)  # Y needs Z (P2)
        TaskDependency.objects.create(task=z, depends_on_task=self.x)  # Z needs X
        form = TaskDependencyForm({"depends_on_task": self.y.pk}, task=self.x)  # X needs Y closes the loop
        self.assertFalse(form.is_valid())
        self.assertIn("cycle", str(form.errors))
