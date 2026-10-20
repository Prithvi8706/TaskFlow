from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import CategoryForm, MilestoneForm, ProjectForm, TagForm, TaskForm
from .models import Category, Milestone, Project, Tag, Task


# ---------------------------------------------------------------- projects


@login_required
def project_list(request):
    projects = (
        Project.objects.filter(owner=request.user)
        .annotate(
            total_tasks=Count("tasks"),
            completed_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED)),
        )
        .order_by("deadline", "name")
    )
    return render(request, "tracker/project_list.html", {"projects": projects})


@login_required
def project_detail(request, pk):
    project = get_object_or_404(Project, pk=pk, owner=request.user)
    tasks = project.tasks.select_related("milestone", "category").prefetch_related("tags").order_by("deadline", "title")
    milestones = project.milestones.annotate(
        total_tasks=Count("tasks"),
        completed_tasks=Count("tasks", filter=Q(tasks__status=Task.Status.COMPLETED)),
    )
    counts = tasks.aggregate(
        total=Count("task_id"),
        completed=Count("task_id", filter=Q(status=Task.Status.COMPLETED)),
    )
    return render(
        request,
        "tracker/project_detail.html",
        {"project": project, "tasks": tasks, "milestones": milestones, "counts": counts},
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


def user_tasks(user):
    return (
        Task.objects.filter(project__owner=user)
        .select_related("project", "milestone", "category")
        .prefetch_related("tags")
    )


@login_required
def task_list(request):
    tasks = user_tasks(request.user).order_by("deadline", "title")
    return render(request, "tracker/task_list.html", {"tasks": tasks})


@login_required
def task_detail(request, pk):
    task = get_object_or_404(user_tasks(request.user), pk=pk)
    return render(request, "tracker/task_detail.html", {"task": task})


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
