from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, Count, F, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    CategoryForm,
    MilestoneForm,
    ProjectForm,
    TagForm,
    TaskDependencyForm,
    TaskFilterForm,
    TaskForm,
)
from .models import Category, Milestone, MilestoneProgress, Project, ProjectProgress, Tag, Task, TaskDependency


# ---------------------------------------------------------------- projects


@login_required
def project_list(request):
    # Progress numbers come from the v_project_progress view (OneToOne `progress`).
    projects = Project.objects.filter(owner=request.user).select_related("progress").order_by("deadline", "name")
    return render(request, "tracker/project_list.html", {"projects": projects})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    tasks = (
        project.tasks.select_related("milestone", "category")
        .prefetch_related("tags")
        .annotate(open_prereqs=OPEN_PREREQS)
        .order_by("deadline", "title")
    )
    milestones = project.milestones.select_related("progress")
    progress = ProjectProgress.objects.get(project=project)
    return render(
        request,
        "tracker/project_detail.html",
        {
            "project": project,
            "tasks": tasks,
            "milestones": milestones,
            "progress": progress,
            "status_choices": Task.Status.choices,
        },
    )


@login_required
def project_create(request):
    form = ProjectForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Project “{project.name}” created.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/project_form.html", {"form": form})


@login_required
def project_edit(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    form = ProjectForm(request.POST or None, instance=project, owner=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Project updated.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/project_form.html", {"form": form, "project": project})


@login_required
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    if request.method == "POST":
        name = project.name
        project.delete()
        messages.success(request, f"Project “{name}” deleted.")
        return redirect("project_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": project,
            "kind": "project",
            "warning": "All of its milestones, tasks and task history will be deleted too.",
            "cancel_url": reverse("project_list"),
        },
    )


# -------------------------------------------------------------- milestones


@login_required
def milestone_create(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, owner=request.user)
    form = MilestoneForm(request.POST or None, project=project)
    if request.method == "POST" and form.is_valid():
        milestone = form.save()
        messages.success(request, f"Milestone “{milestone.name}” added.")
        return redirect("project_detail", pk=project.pk)
    return render(request, "tracker/milestone_form.html", {"form": form, "project": project})


@login_required
def milestone_edit(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk, project__owner=request.user)
    project = milestone.project
    form = MilestoneForm(request.POST or None, instance=milestone, project=project)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Milestone updated.")
        return redirect("project_detail", pk=project.pk)
    return render(
        request, "tracker/milestone_form.html", {"form": form, "project": project, "milestone": milestone}
    )


@login_required
def milestone_delete(request, pk):
    milestone = get_object_or_404(Milestone, pk=pk, project__owner=request.user)
    project = milestone.project
    if request.method == "POST":
        milestone.delete()
        messages.success(request, f"Milestone “{milestone.name}” deleted.")
        return redirect("project_detail", pk=project.pk)
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": milestone,
            "kind": "milestone",
            "warning": "Its tasks stay in the project but are no longer linked to a milestone.",
            "cancel_url": reverse("project_detail", args=[project.pk]),
        },
    )


# ------------------------------------------------------------------- tasks


# Number of prerequisites that are not completed; > 0 means the task is blocked.
OPEN_PREREQS = Count(
    "prerequisite_links",
    filter=~Q(prerequisite_links__depends_on_task__status=Task.Status.COMPLETED),
)


def user_tasks(user):
    return (
        Task.objects.filter(project__owner=user)
        .select_related("project", "milestone", "category")
        .prefetch_related("tags")
        .annotate(open_prereqs=OPEN_PREREQS)
    )


PRIORITY_RANK = Case(
    When(priority=Task.Priority.HIGH, then=Value(3)),
    When(priority=Task.Priority.MEDIUM, then=Value(2)),
    default=Value(1),
    output_field=IntegerField(),
)

SORT_ORDER = {
    "deadline": [F("deadline").asc(nulls_last=True), "title"],
    "priority": [PRIORITY_RANK.desc(), F("deadline").asc(nulls_last=True), "title"],
    "created": ["-created_at", "title"],
}


def filtered_tasks(request):
    """Apply the search / filter / sort query string to the user's tasks."""
    form = TaskFilterForm(request.GET or None, user=request.user)
    tasks = user_tasks(request.user)
    sort = "deadline"
    if form.is_valid():
        data = form.cleaned_data
        if data["q"]:
            tasks = tasks.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"]))
        if data["status"]:
            tasks = tasks.filter(status=data["status"])
        if data["priority"]:
            tasks = tasks.filter(priority=data["priority"])
        if data["project"]:
            tasks = tasks.filter(project=data["project"])
        if data["category"]:
            tasks = tasks.filter(category=data["category"])
        if data["tag"]:
            tasks = tasks.filter(tags=data["tag"])
        sort = data["sort"] or sort
    return form, tasks.order_by(*SORT_ORDER[sort])


@login_required
def task_list(request):
    form, tasks = filtered_tasks(request)
    is_filtered = any(v for k, v in request.GET.items() if k != "sort")
    return render(
        request,
        "tracker/task_list.html",
        {"tasks": tasks, "filter_form": form, "is_filtered": is_filtered, "status_choices": Task.Status.choices},
    )


@login_required
def task_detail(request, pk):
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    return render_task_detail(request, task, TaskDependencyForm(task=task))


def render_task_detail(request, task, dep_form):
    prerequisites = task.prerequisite_links.select_related("depends_on_task").order_by("depends_on_task__title")
    dependents = task.dependent_links.select_related("task").order_by("task__title")
    return render(
        request,
        "tracker/task_detail.html",
        {
            "task": task,
            "prerequisites": prerequisites,
            "dependents": dependents,
            "dep_form": dep_form,
            "status_choices": Task.Status.choices,
            "history": task.history.order_by("-changed_at", "-history_id"),
        },
    )


@login_required
@require_POST
def task_status_update(request, pk):
    """Quick status change from the task list or task page."""
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    new_status = request.POST.get("status")
    if new_status not in Task.Status.values:
        messages.error(request, "Unknown status.")
    elif new_status == Task.Status.COMPLETED and task.open_prerequisites():
        names = ", ".join(t.title for t in task.open_prerequisites())
        messages.error(request, f"“{task.title}” is waiting on: {names}.")
    elif new_status != task.status:
        task.status = new_status
        task.save(update_fields=["status"])
        messages.success(request, f"“{task.title}” moved to {task.get_status_display()}.")

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("task_detail", pk=task.pk)


@login_required
def dependency_add(request, pk):
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    if request.method != "POST":
        return redirect("task_detail", pk=task.pk)
    form = TaskDependencyForm(request.POST, task=task)
    if not form.is_valid():
        # Re-render so the rejection (self-dependency, duplicate, cycle) shows on the form.
        return render_task_detail(request, task, form)
    dep = form.save()
    messages.success(request, f"“{task.title}” now depends on “{dep.depends_on_task.title}”.")
    return redirect("task_detail", pk=task.pk)


@login_required
def dependency_delete(request, pk):
    dep = get_object_or_404(TaskDependency, pk=pk, task__project__owner=request.user)
    if request.method == "POST":
        dep.delete()
        messages.success(request, "Prerequisite removed.")
    return redirect("task_detail", pk=dep.task_id)


@login_required
def task_create(request):
    initial = {}
    project_id = request.GET.get("project")
    if project_id and project_id.isdigit():
        initial["project"] = Project.objects.filter(owner=request.user, pk=project_id).first()
    form = TaskForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        task = form.save()
        messages.success(request, f"Task “{task.title}” created.")
        return redirect("task_detail", pk=task.pk)
    return render(request, "tracker/task_form.html", {"form": form})


@login_required
def task_edit(request, pk):
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    form = TaskForm(request.POST or None, instance=task, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Task updated.")
        return redirect("task_detail", pk=task.pk)
    return render(request, "tracker/task_form.html", {"form": form, "task": task})


@login_required
def task_delete(request, pk):
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    if request.method == "POST":
        project_pk = task.project_id
        task.delete()
        messages.success(request, f"Task “{task.title}” deleted.")
        return redirect("project_detail", pk=project_pk)
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": task,
            "kind": "task",
            "warning": "Its status history and dependency links will be deleted too.",
            "cancel_url": reverse("task_detail", args=[task.pk]),
        },
    )


# -------------------------------------------------------------- categories


@login_required
def category_list(request):
    form = CategoryForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        messages.success(request, f"Category “{category.name}” added.")
        return redirect("category_list")
    categories = Category.objects.filter(owner=request.user).annotate(task_count=Count("tasks"))
    return render(request, "tracker/category_list.html", {"form": form, "categories": categories})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk, owner=request.user)
    if request.method == "POST":
        category.delete()
        messages.success(request, f"Category “{category.name}” deleted.")
        return redirect("category_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": category,
            "kind": "category",
            "warning": "Tasks in this category are kept and become uncategorised.",
            "cancel_url": reverse("category_list"),
        },
    )


# -------------------------------------------------------------------- tags


@login_required
def tag_list(request):
    form = TagForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        tag = form.save()
        messages.success(request, f"Tag “{tag.name}” added.")
        return redirect("tag_list")
    tags = Tag.objects.filter(owner=request.user).annotate(task_count=Count("tasks"))
    return render(request, "tracker/tag_list.html", {"form": form, "tags": tags})


@login_required
def tag_delete(request, pk):
    tag = get_object_or_404(Tag, pk=pk, owner=request.user)
    if request.method == "POST":
        tag.delete()
        messages.success(request, f"Tag “{tag.name}” deleted.")
        return redirect("tag_list")
    return render(
        request,
        "tracker/confirm_delete.html",
        {
            "object": tag,
            "kind": "tag",
            "warning": "It is removed from every task (its task_tag rows are deleted).",
            "cancel_url": reverse("tag_list"),
        },
    )
