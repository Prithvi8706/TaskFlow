from django.contrib import admin

from .models import Category, Milestone, Project, Tag, Task, TaskDependency, TaskHistory, TaskTag


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    list_filter = ("owner",)
    search_fields = ("name",)


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "status", "start_date", "deadline", "created_at")
    list_filter = ("status", "owner")
    search_fields = ("name", "description")
    inlines = [MilestoneInline]


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "status", "deadline")
    list_filter = ("status", "project")
    search_fields = ("name",)


class TaskTagInline(admin.TabularInline):
    model = TaskTag
    extra = 0


class PrerequisiteInline(admin.TabularInline):
    model = TaskDependency
    fk_name = "task"
    extra = 0
    verbose_name = "prerequisite"
    verbose_name_plural = "prerequisites"


class TaskHistoryInline(admin.TabularInline):
    model = TaskHistory
    extra = 0
    can_delete = False
    readonly_fields = ("old_status", "new_status", "changed_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "project", "milestone", "status", "priority", "deadline", "completed_at")
    list_filter = ("status", "priority", "project", "category")
    search_fields = ("title", "description")
    readonly_fields = ("completed_at",)
    inlines = [TaskTagInline, PrerequisiteInline, TaskHistoryInline]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "owner")
    search_fields = ("name",)


@admin.register(TaskDependency)
class TaskDependencyAdmin(admin.ModelAdmin):
    list_display = ("task", "depends_on_task")


@admin.register(TaskHistory)
class TaskHistoryAdmin(admin.ModelAdmin):
    """Read-only: history rows are written by the database trigger only."""

    list_display = ("task", "old_status", "new_status", "changed_at")
    list_filter = ("new_status",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
