"""
TaskFlow schema.

Every model sets an explicit `db_table` and primary-key column name so the
raw SQL in `sql/` reads naturally (e.g. `project.project_id`).
"""

from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Now
from django.utils import timezone


class Category(models.Model):
    category_id = models.BigAutoField(primary_key=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=60)

    class Meta:
        db_table = "category"
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uq_category_owner_name"),
        ]

    def __str__(self):
        return self.name


class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        ON_HOLD = "ON_HOLD", "On hold"

    project_id = models.BigAutoField(primary_key=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="", db_default="")
    start_date = models.DateField()
    deadline = models.DateField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PLANNED, db_default=Status.PLANNED
    )
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())

    class Meta:
        db_table = "project"
        ordering = ["deadline", "name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uq_project_owner_name"),
            models.CheckConstraint(
                condition=Q(deadline__gte=F("start_date")), name="ck_project_deadline_after_start"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PLANNED", "ACTIVE", "COMPLETED", "ON_HOLD"]),
                name="ck_project_status",
            ),
        ]

    def __str__(self):
        return self.name


class Milestone(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"

    milestone_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="", db_default="")
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_default=Status.PENDING
    )

    class Meta:
        db_table = "milestone"
        ordering = ["deadline", "name"]
        constraints = [
            models.UniqueConstraint(fields=["project", "name"], name="uq_milestone_project_name"),
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "IN_PROGRESS", "COMPLETED"]),
                name="ck_milestone_status",
            ),
        ]

    def __str__(self):
        return self.name


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        BLOCKED = "BLOCKED", "Blocked"
        COMPLETED = "COMPLETED", "Completed"

    task_id = models.BigAutoField(primary_key=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks")
    milestone = models.ForeignKey(
        Milestone, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="", db_default="")
    priority = models.CharField(
        max_length=8, choices=Priority.choices, default=Priority.MEDIUM, db_default=Priority.MEDIUM
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_default=Status.PENDING
    )
    created_at = models.DateTimeField(default=timezone.now, db_default=Now())
    deadline = models.DateField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "task"
        ordering = ["deadline", "title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(priority__in=["LOW", "MEDIUM", "HIGH"]), name="ck_task_priority"
            ),
            models.CheckConstraint(
                condition=Q(status__in=["PENDING", "IN_PROGRESS", "BLOCKED", "COMPLETED"]),
                name="ck_task_status",
            ),
        ]

    def __str__(self):
        return self.title

    @property
    def is_overdue(self):
        return (
            self.deadline is not None
            and self.status != self.Status.COMPLETED
            and self.deadline < timezone.localdate()
        )
