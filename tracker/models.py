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
