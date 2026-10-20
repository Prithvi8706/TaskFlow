"""
Load reproducible demo data: 2 users, 4 projects, 12 milestones, 60 tasks.

    python manage.py seed_demo

Re-running wipes and recreates the two demo users (and, through ON DELETE
CASCADE, everything they own). A fixed random seed keeps the data identical
between runs; dates are relative to today so some tasks are always overdue.

Tasks are inserted as PENDING and then moved through their statuses with
ordinary UPDATEs, so the database trigger writes task_history and stamps
completed_at exactly as it would for a real user. Because that all happens in
one run, the trigger-written timestamps are then spread back over each task's
lifetime (creation -> on or before its deadline), so the history timeline and
"average days to complete" look like work done over weeks, not milliseconds.
"""

import datetime as dt
import random

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tracker.models import Category, Milestone, Project, Tag, Task, TaskDependency, TaskHistory, TaskTag

SEED = 42

USERS = [
    ("demo", "demo@taskflow.local", "Demo", "User"),
    ("alex", "alex@taskflow.local", "Alex", "Morgan"),
]
DEMO_PASSWORD = "taskflow-demo"

CATEGORIES = ["Backend", "Frontend", "Design", "QA", "DevOps", "Docs"]
TAGS = ["bug", "feature", "urgent", "research", "client", "refactor"]

# (owner, name, description, status, started_days_ago, duration_days, completion_bias, milestones, tasks)
PROJECTS = [
    (
        "demo",
        "Website Redesign",
        "Rebuild the marketing site with a new design system and CMS.",
        Project.Status.ACTIVE, 80, 140, 0.70,
        ["Discovery & wireframes", "Design system", "Build & launch"],
        [
            ("Stakeholder interviews", "Design"), ("Audit current site analytics", "QA"),
            ("Draft sitemap", "Design"), ("Low-fidelity wireframes", "Design"),
            ("Choose headless CMS", "Backend"), ("Colour and type tokens", "Design"),
            ("Component library in Storybook", "Frontend"), ("Navigation component", "Frontend"),
            ("CMS content model", "Backend"), ("Migrate blog posts", "Backend"),
            ("Accessibility review", "QA"), ("Responsive layout pass", "Frontend"),
            ("Set up CDN and caching", "DevOps"), ("Write launch checklist", "Docs"),
            ("Cross-browser testing", "QA"),
        ],
    ),
    (
        "demo",
        "Mobile App Launch",
        "Ship v1 of the iOS and Android companion app.",
        Project.Status.ACTIVE, 60, 120, 0.50,
        ["MVP features", "Beta programme", "Store release"],
        [
            ("Define MVP scope", "Docs"), ("Auth flow with refresh tokens", "Backend"),
            ("Push notification service", "Backend"), ("Onboarding screens", "Frontend"),
            ("Offline sync", "Backend"), ("Crash reporting", "DevOps"),
            ("Dark mode support", "Frontend"), ("Recruit beta testers", "Docs"),
            ("Beta feedback triage", "QA"), ("Fix login crash on Android 12", "Frontend"),
            ("Performance profiling", "QA"), ("App store screenshots", "Design"),
            ("Privacy policy update", "Docs"), ("CI pipeline for builds", "DevOps"),
            ("Submit to app stores", "DevOps"),
        ],
    ),
    (
        "demo",
        "Data Warehouse Migration",
        "Move reporting from the legacy MySQL replica to a columnar warehouse.",
        Project.Status.ON_HOLD, 45, 150, 0.30,
        ["Assessment", "Pipeline build", "Cut-over"],
        [
            ("Inventory existing reports", "Docs"), ("Estimate storage costs", "DevOps"),
            ("Pick warehouse vendor", "Backend"), ("Design star schema", "Backend"),
            ("Build ingestion jobs", "Backend"), ("Backfill historical data", "Backend"),
            ("Data quality checks", "QA"), ("Rewrite revenue dashboard", "Frontend"),
            ("Access control and roles", "DevOps"), ("Load testing", "QA"),
            ("Parallel-run validation", "QA"), ("Train analysts", "Docs"),
            ("Decommission old replica", "DevOps"), ("Runbook for on-call", "Docs"),
            ("Cost monitoring alerts", "DevOps"),
        ],
    ),
    (
        "alex",
        "Q4 Marketing Campaign",
        "Plan and run the end-of-year product campaign.",
        Project.Status.ACTIVE, 50, 100, 0.55,
        ["Planning", "Content production", "Launch & measure"],
        [
            ("Campaign brief", "Docs"), ("Audience segmentation", "Backend"),
            ("Budget approval", "Docs"), ("Landing page copy", "Docs"),
            ("Landing page design", "Design"), ("Email templates", "Design"),
            ("Video storyboard", "Design"), ("Set up UTM tracking", "Backend"),
            ("A/B test subject lines", "QA"), ("Partner outreach", "Docs"),
            ("Paid social creatives", "Design"), ("Schedule email sends", "DevOps"),
            ("Launch day monitoring", "DevOps"), ("Weekly performance report", "Docs"),
            ("Post-campaign retrospective", "Docs"),
        ],
    ),
]


class Command(BaseCommand):
    help = "Wipe and recreate reproducible demo data (users demo/alex)."

    def handle(self, *args, **options):
        rng = random.Random(SEED)
        today = timezone.localdate()
        now = timezone.now()

        with transaction.atomic():
            User.objects.filter(username__in=[u[0] for u in USERS]).delete()

            users, categories, tags = {}, {}, {}
            for username, email, first, last in USERS:
                user = User.objects.create_user(
                    username, email, DEMO_PASSWORD, first_name=first, last_name=last
                )
                users[username] = user
                categories[username] = {
                    name: Category.objects.create(owner=user, name=name) for name in CATEGORIES
                }
                tags[username] = {name: Tag.objects.create(owner=user, name=name) for name in TAGS}

            for spec in PROJECTS:
                self._seed_project(rng, today, now, users, categories, tags, *spec)

        self._report()

    # ------------------------------------------------------------------

    def _seed_project(self, rng, today, now, users, categories, tags, owner_name, name, description,
                      status, started_ago, duration, bias, milestone_names, task_specs):
        owner = users[owner_name]
        start = today - dt.timedelta(days=started_ago)
        end = start + dt.timedelta(days=duration)
        project = Project.objects.create(
            owner=owner, name=name, description=description, status=status,
            start_date=start, deadline=end, created_at=_at(start, rng),
        )

        milestones = [
            Milestone.objects.create(
                project=project, name=m_name,
                deadline=start + dt.timedelta(days=round(duration * (i + 1) / len(milestone_names))),
            )
            for i, m_name in enumerate(milestone_names)
        ]

        n = len(task_specs)
        per_milestone = -(-n // len(milestones))  # ceil

        # 1. Decide each task's final status. Earlier tasks are more likely done.
        final = []
        for i in range(n):
            position = i / n
            if rng.random() < bias + 0.25 - position:
                final.append(Task.Status.COMPLETED)
            else:
                final.append(rng.choices(
                    [Task.Status.IN_PROGRESS, Task.Status.PENDING, Task.Status.BLOCKED], weights=[5, 4, 1]
                )[0])

        # 2. Decide dependencies (always from a later task to an earlier one,
        #    so the graph is acyclic by construction).
        deps = {(5, 4), (4, 3), (3, 2)}  # a guaranteed 4-task chain for the recursive query
        for i in range(1, n):
            if rng.random() < 0.35:
                deps.add((i, rng.randrange(max(0, i - 4), i)))
        # A completed task cannot have an open prerequisite: complete the prerequisite.
        changed = True
        while changed:
            changed = False
            for task_i, pre_i in deps:
                if final[task_i] == Task.Status.COMPLETED and final[pre_i] != Task.Status.COMPLETED:
                    final[pre_i] = Task.Status.COMPLETED
                    changed = True
        # A task in progress with an open prerequisite is really blocked.
        for task_i, pre_i in deps:
            if final[pre_i] != Task.Status.COMPLETED and final[task_i] == Task.Status.IN_PROGRESS:
                final[task_i] = Task.Status.BLOCKED

        # 3. Insert every task as PENDING (trigger logs NULL -> PENDING).
        elapsed = max((today - start).days, 1)
        remaining = max((end - today).days, 5)
        tasks = []
        for i, (title, category) in enumerate(task_specs):
            if final[i] == Task.Status.COMPLETED:
                deadline = start + dt.timedelta(days=rng.randint(5, elapsed))
            elif rng.random() < 0.3:
                deadline = today - dt.timedelta(days=rng.randint(1, 20))  # overdue
            else:
                deadline = today + dt.timedelta(days=rng.randint(3, remaining))
            created = start + dt.timedelta(days=rng.randint(0, max(0, min(elapsed - 1, (deadline - start).days))))
            task = Task.objects.create(
                project=project,
                milestone=None if i % 7 == 6 else milestones[min(i // per_milestone, len(milestones) - 1)],
                category=categories[owner_name][category],
                title=title,
                description=f"{title} for {name}.",
                priority=rng.choices(list(Task.Priority.values), weights=[3, 5, 3])[0],
                deadline=deadline,
                created_at=_at(created, rng),
            )
            tasks.append(task)
            for tag_name in rng.sample(TAGS, k=rng.choice([0, 1, 1, 2])):
                TaskTag.objects.create(task=task, tag=tags[owner_name][tag_name])

        for task_i, pre_i in sorted(deps):
            TaskDependency.objects.create(task=tasks[task_i], depends_on_task=tasks[pre_i])

        # 4. Walk each task to its final status with real UPDATEs so the
        #    trigger records every step in task_history.
        for task, target in zip(tasks, final):
            for step in _status_path(target, rng):
                task.status = step
                task.save(update_fields=["status"])

        # 4b. Spread the trigger-written timestamps over each task's lifetime.
        for i, (task, target) in enumerate(zip(tasks, final)):
            _backdate_history(task, target, random.Random(f"{SEED}:{name}:{i}"), now)

        # 5. Milestone status follows its tasks.
        for milestone in milestones:
            statuses = list(milestone.tasks.values_list("status", flat=True))
            if statuses and all(s == Task.Status.COMPLETED for s in statuses):
                milestone.status = Milestone.Status.COMPLETED
            elif any(s != Task.Status.PENDING for s in statuses):
                milestone.status = Milestone.Status.IN_PROGRESS
            milestone.save(update_fields=["status"])

    def _report(self):
        owned = {"project__owner__username__in": [u[0] for u in USERS]}
        today = timezone.localdate()
        rows = [
            ("users", User.objects.filter(username__in=[u[0] for u in USERS]).count()),
            ("projects", Project.objects.filter(owner__username__in=[u[0] for u in USERS]).count()),
            ("milestones", Milestone.objects.filter(**owned).count()),
            ("tasks", Task.objects.filter(**owned).count()),
            ("  completed", Task.objects.filter(**owned, status=Task.Status.COMPLETED).count()),
            ("  in progress", Task.objects.filter(**owned, status=Task.Status.IN_PROGRESS).count()),
            ("  blocked", Task.objects.filter(**owned, status=Task.Status.BLOCKED).count()),
            ("  pending", Task.objects.filter(**owned, status=Task.Status.PENDING).count()),
            ("  overdue", Task.objects.filter(**owned, deadline__lt=today).exclude(status=Task.Status.COMPLETED).count()),
            ("dependencies", TaskDependency.objects.filter(task__project__owner__username__in=[u[0] for u in USERS]).count()),
            ("task_tag rows", TaskTag.objects.filter(task__project__owner__username__in=[u[0] for u in USERS]).count()),
            ("task_history rows (trigger)", TaskHistory.objects.filter(task__project__owner__username__in=[u[0] for u in USERS]).count()),
        ]
        self.stdout.write(self.style.SUCCESS("Demo data loaded."))
        for label, value in rows:
            self.stdout.write(f"  {label:<30}{value}")
        self.stdout.write(f"Log in as demo / {DEMO_PASSWORD} (or alex / {DEMO_PASSWORD}).")


def _at(day, rng):
    """A timezone-aware datetime on `day` during working hours."""
    naive = dt.datetime.combine(day, dt.time(rng.randint(8, 18), rng.choice([0, 15, 30, 45])))
    return timezone.make_aware(naive)


def _backdate_history(task, target, rng, now):
    """
    Re-time the task_history rows the trigger just wrote (all stamped "now")
    so they run from the task's creation to a plausible finish, and make
    completed_at match the final COMPLETED step. Row order is unchanged.
    """
    rows = list(TaskHistory.objects.filter(task=task).order_by("history_id"))
    start = task.created_at
    if target == Task.Status.COMPLETED:
        finish_day = task.deadline - dt.timedelta(days=rng.randint(0, 4))
        finish = timezone.make_aware(dt.datetime.combine(finish_day, dt.time(rng.randint(9, 17), rng.randint(0, 59))))
    else:
        finish = now - dt.timedelta(hours=rng.randint(2, 72))
    finish = min(max(finish, start + dt.timedelta(hours=2)), now - dt.timedelta(minutes=5))

    steps = len(rows) - 1
    stamps = [start]
    for j in range(1, steps + 1):
        if j == steps:
            stamps.append(finish)
        else:
            share = (j + rng.uniform(-0.3, 0.3)) / steps
            stamps.append(max(stamps[-1], start + (finish - start) * share))
    for row, stamp in zip(rows, stamps):
        TaskHistory.objects.filter(pk=row.pk).update(changed_at=stamp)
    if target == Task.Status.COMPLETED:
        # Status is unchanged, so trg_task_completed_at keeps this value.
        Task.objects.filter(pk=task.pk).update(completed_at=finish)


def _status_path(target, rng):
    """Status steps from PENDING to `target` (PENDING itself needs no update)."""
    S = Task.Status
    if target == S.PENDING:
        return []
    if target == S.IN_PROGRESS:
        return [S.IN_PROGRESS]
    if target == S.BLOCKED:
        return [S.IN_PROGRESS, S.BLOCKED] if rng.random() < 0.6 else [S.BLOCKED]
    # COMPLETED: sometimes it got blocked along the way.
    if rng.random() < 0.25:
        return [S.IN_PROGRESS, S.BLOCKED, S.IN_PROGRESS, S.COMPLETED]
    return [S.IN_PROGRESS, S.COMPLETED]
