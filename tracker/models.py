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
    tags = models.ManyToManyField("Tag", through="TaskTag", related_name="tasks", blank=True)

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

    def open_prerequisites(self):
        """Prerequisite tasks that are not completed yet."""
        return list(
            Task.objects.filter(dependent_links__task=self).exclude(status=Task.Status.COMPLETED).order_by("title")
        )

    @property
    def is_overdue(self):
        return (
            self.deadline is not None
            and self.status != self.Status.COMPLETED
            and self.deadline < timezone.localdate()
        )


class Tag(models.Model):
    tag_id = models.BigAutoField(primary_key=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tags")
    name = models.CharField(max_length=40)

    class Meta:
        db_table = "tag"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="uq_tag_owner_name"),
        ]

    def __str__(self):
        return self.name


class TaskTag(models.Model):
    """Junction table resolving the task M:N tag relationship."""

    task_tag_id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        db_table = "task_tag"
        constraints = [
            models.UniqueConstraint(fields=["task", "tag"], name="uq_task_tag"),
        ]

    def __str__(self):
        return f"{self.task} #{self.tag}"


class TaskDependency(models.Model):
    """
    Recursive M:N on task: `task` cannot start until `depends_on_task` is completed.

    The CHECK constraint stops a task depending on itself. Longer cycles
    (A -> B -> A) span several rows, which a CHECK cannot see, so those are
    rejected in the application layer (see TaskDependencyForm.clean).
    """

    dependency_id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="prerequisite_links")
    depends_on_task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="dependent_links")

    class Meta:
        db_table = "task_dependency"
        constraints = [
            models.UniqueConstraint(fields=["task", "depends_on_task"], name="uq_task_dependency"),
            models.CheckConstraint(
                condition=~Q(task=F("depends_on_task")), name="ck_task_dependency_not_self"
            ),
        ]

    def __str__(self):
        return f"{self.task} depends on {self.depends_on_task}"


class TaskHistory(models.Model):
    """
    Audit trail of task status changes.

    Rows are written only by the PostgreSQL trigger `trg_task_status_history`
    (see sql/triggers.sql); the application never inserts into this table.
    """

    history_id = models.BigAutoField(primary_key=True)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="history")
    old_status = models.CharField(max_length=12, choices=Task.Status.choices, null=True, blank=True)
    new_status = models.CharField(max_length=12, choices=Task.Status.choices)
    changed_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "task_history"
        ordering = ["changed_at", "history_id"]
        verbose_name_plural = "task history"
        indexes = [models.Index(fields=["task", "changed_at"], name="ix_task_history_task_time")]

    def __str__(self):
        return f"{self.task}: {self.old_status} -> {self.new_status}"


# ---------------------------------------------------------------------------
# Read-only models over the PostgreSQL views in sql/views.sql.
# managed = False: Django never creates, alters or drops these.
# ---------------------------------------------------------------------------


class ProjectProgress(models.Model):
    project = models.OneToOneField(
        Project, on_delete=models.DO_NOTHING, primary_key=True, db_column="project_id", related_name="progress"
    )
    owner = models.ForeignKey(User, on_delete=models.DO_NOTHING, db_column="owner_id", related_name="+")
    name = models.CharField(max_length=120)
    total_tasks = models.IntegerField()
    completed_tasks = models.IntegerField()
    overdue_tasks = models.IntegerField()
    completion_pct = models.DecimalField(max_digits=5, decimal_places=1)

    class Meta:
        managed = False
        db_table = "v_project_progress"

    def __str__(self):
        return f"{self.name}: {self.completion_pct}%"


class MilestoneProgress(models.Model):
    milestone = models.OneToOneField(
        Milestone, on_delete=models.DO_NOTHING, primary_key=True, db_column="milestone_id", related_name="progress"
    )
    project = models.ForeignKey(Project, on_delete=models.DO_NOTHING, db_column="project_id", related_name="+")
    name = models.CharField(max_length=120)
    total_tasks = models.IntegerField()
    completed_tasks = models.IntegerField()
    completion_pct = models.DecimalField(max_digits=5, decimal_places=1)

    class Meta:
        managed = False
        db_table = "v_milestone_progress"

    def __str__(self):
        return f"{self.name}: {self.completion_pct}%"
