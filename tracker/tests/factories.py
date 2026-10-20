import datetime as dt

from django.contrib.auth.models import User

from tracker.models import Milestone, Project, Task

START = dt.date(2026, 1, 1)


def make_user(username="alice"):
    return User.objects.create_user(username, f"{username}@example.com", "test-pass-123")


def make_project(owner, name="Apollo", **kwargs):
    kwargs.setdefault("start_date", START)
    kwargs.setdefault("deadline", START + dt.timedelta(days=90))
    return Project.objects.create(owner=owner, name=name, **kwargs)


def make_milestone(project, name="M1", **kwargs):
    return Milestone.objects.create(project=project, name=name, **kwargs)


def make_task(project, title="Task", **kwargs):
    return Task.objects.create(project=project, title=title, **kwargs)
